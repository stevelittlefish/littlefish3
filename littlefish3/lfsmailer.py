"""
Code to send email messages via an SMTP server
"""

import logging
from email.mime.text import MIMEText
import smtplib
import json
import traceback
import pprint
import email.utils
import re
from uuid import UUID
import datetime

from . import timetool

__author__ = 'Stephen Brown (Little Fish Solutions LTD)'

log = logging.getLogger(__name__)

_host = None
_port = None
_username = None
_password = None
_use_tls = None
_default_email_from = None
_email_to_override = None
_dump_email_body = None
_configured = False
_error_reporting_obscured_fields = None

email_regex_string = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
email_regex = re.compile(r'^{}$'.format(email_regex_string))
formatted_address_regex = re.compile(r'^([^,<]+)<({})>$'.format(email_regex_string))
error_log_tag_regex = re.compile(r'^(Exception caught: )?\(([^)]+)\)')

DEBUG_ERROR_EMAIL_SENDING = False


class SessionEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)


def init(
    smtp_host: str,
    smtp_port: str,
    smtp_username: str,
    smtp_password: str,
    smtp_use_tls: bool,
    default_email_from: str | None = None,
    email_to_override: str | None = None,
    dump_email_body: bool = False,
):
    """
    Initialise the mailer with the given settings

    :param smtp_host: The SMTP server host
    :param smtp_port: The SMTP server port
    :param smtp_username: The SMTP username
    :param smtp_password: The SMTP password
    :param smtp_use_tls: Use TLS?
    :param default_email_from: The default email from address
    :param email_to_override: If set, all emails will be sent to this address
    :param dump_email_body: If set, all email bodies will be dumped to the log
    """

    global _host, _port, _username, _password, _use_tls, _default_email_from, _email_to_override, \
        _dump_email_body, _configured

    if _configured:
        raise Exception('Multiple calls to {}.init(app)'.format(__name__))

    _host = smtp_host
    _port = smtp_port
    _username = smtp_username
    _password = smtp_password
    _use_tls = smtp_use_tls

    log.info('LFS Mailer using {}@{}:{}{}'.format(_username, _host, _port, ' (TLS)' if _use_tls else ''))

    _default_email_from = default_email_from

    # If this is set, we will send all emails here
    _email_to_override = email_to_override
    # Whether or not to dump the email body
    _dump_email_body = dump_email_body

    _configured = True


def format_address(email_address, name=None):
    if name is None:
        return email_address
    return '{} <{}>'.format(name, email_address)


def parse_address(formatted_address):
    """
    :param formatted_address: A string like "email@address.com" or "My Email <email@address.com>"
    
    :return: Tuple: (address, name)
    """
    if email_regex.match(formatted_address):
        # Just a raw address
        return (formatted_address, None)
    
    match = formatted_address_regex.match(formatted_address)

    if match:
        (name, email) = match.group(1, 2)
        return email.strip(), name.strip()

    raise ValueError('"{}" is not a valid formatted address'.format(formatted_address))


def send_text_mail_single(to_email_address, to_name, subject, body, from_address=None):
    to = format_address(to_email_address, to_name)

    send_text_mail([to], subject, body, from_address)


def send_text_mail(recipient_list, subject, body, from_address=None):
    send_mail(recipient_list, subject, body, html=False, from_address=from_address)


def send_html_mail_single(to_email_address, to_name, subject, body, from_address=None):
    to = format_address(to_email_address, to_name)

    send_html_mail([to], subject, body, from_address)


def send_html_mail(recipient_list, subject, body, from_address=None):
    send_mail(recipient_list, subject, body, html=True, from_address=from_address)


def send_mail(recipient_list, subject, body, html=False, from_address=None):
    """
    :param recipient_list: List of recipients i.e. ['testing@fig14.com', 'Stephen Brown <steve@fig14.com>']
    :param subject: The subject
    :param body: The email body
    :param html: Is this a html email? Defaults to False
    :param from_address: From email address or name and address i.e. 'Test System <errors@test.com>
    :return:
    """
    if not _configured:
        raise Exception('LFS Mailer hasn\'t been configured')

    if from_address is None:
        from_address = _default_email_from
    
    mime_type = 'html' if html else 'plain'
    log.debug('Sending {} mail to {}: {}'.format(mime_type, ', '.join(recipient_list), subject))
    if _dump_email_body:
        log.info(body)

    s = smtplib.SMTP(_host, _port)

    if _use_tls:
        s.ehlo()
        s.starttls()
        s.ehlo()
    
    if _username:
        s.login(_username, _password)

    if _email_to_override:
        subject = '[to %s] %s' % (', '.join(recipient_list), subject)
        recipient_list = [_email_to_override]
        log.info('Using email override: %s' % ', '.join(recipient_list))

    msg = MIMEText(body, mime_type, 'utf-8')
    msg['To'] = ', '.join(recipient_list)
    msg['Subject'] = subject
    msg['From'] = from_address
    msg['Date'] = email.utils.formatdate()

    s.sendmail(from_address, recipient_list, msg.as_string())
    s.quit()


class LfsSmtpHandler(logging.Handler):
    """
    A handler class which sends an SMTP email for each logging event.  This has been customised to (easily) work with
    lfsmailer
    """
    def __init__(self, fromaddr, toaddrs, subject, max_sends_per_minute=15):
        """
        Initialize the handler.

        Initialize the instance with the from and to addresses and subject
        line of the email. To specify a non-standard SMTP port, use the
        (host, port) tuple format for the mailhost argument. To specify
        authentication credentials, supply a (username, password) tuple
        for the credentials argument. To specify the use of a secure
        protocol (TLS), pass in a tuple for the secure argument. This will
        only be used when authentication credentials are supplied. The tuple
        will be either an empty tuple, or a single-value tuple with the name
        of a keyfile, or a 2-value tuple with the names of the keyfile and
        certificate file. (This tuple is passed to the `starttls` method).
        """
        super(LfsSmtpHandler, self).__init__()
        self.fromaddr = fromaddr
        if isinstance(toaddrs, str):
            toaddrs = [toaddrs]
        self.toaddrs = toaddrs
        self.subject = subject
        self._timeout = 5.0
        self.max_sends_per_minute = max_sends_per_minute
        self.rate_limiter = []

        # Default formatter
        self.setFormatter(logging.Formatter('''
Message type:       %(levelname)s
Location:           %(pathname)s:%(lineno)d
Module:             %(module)s
Function:           %(funcName)s
Time:               %(asctime)s

Message:

%(message)s
'''))
    
    def add_details(self, message):
        """
        Add extra details to the message.  Separate so that it can be overridden
        """
        msg = message
        # Try to append Flask request details
        try:
            from flask import request
            url = request.url
            method = request.method
            endpoint = request.endpoint

            # Obscure password field and prettify a little bit
            form_dict = dict(request.form)
            for key in form_dict:
                if key.lower() in _error_reporting_obscured_fields:
                    form_dict[key] = '******'
                elif len(form_dict[key]) == 1:
                    form_dict[key] = form_dict[key][0]

            form = pprint.pformat(form_dict).replace('\n', '\n          ')

            msg = '%s\nRequest:\n\nurl:      %s\nmethod:   %s\nendpoint: %s\nform:     %s\n' % \
                (msg, url, method, endpoint, form)
        except Exception:
            traceback.print_exc()

        # Try to append the session
        try:
            from flask import session
            session_str = json.dumps(
                dict(**session),
                indent=2,
                cls=SessionEncoder
            )
            msg = '%s\nSession:\n\n%s\n' % (msg, session_str)
        except Exception:
            traceback.print_exc()
        
        return msg

    def emit(self, record):
        """
        Emit a record.

        Format the record and send it to the specified addressees.
        """
        try:
            # First, remove all records from the rate limiter list that are over a minute old
            now = timetool.unix_time()
            one_minute_ago = now - 60
            new_rate_limiter = [x for x in self.rate_limiter if x > one_minute_ago]
            log.debug('Rate limiter %s -> %s' % (len(self.rate_limiter), len(new_rate_limiter)))
            self.rate_limiter = new_rate_limiter

            # Now, get the number of emails sent in the last minute.  If it's less than the threshold, add another
            # entry to the rate limiter list
            recent_sends = len(self.rate_limiter)
            send_email = recent_sends < self.max_sends_per_minute
            if send_email:
                self.rate_limiter.append(now)

            base_msg = self.format(record)
            msg = self.add_details(base_msg)

            # If the messages starts with a bracketted string i.e. (Health Check) then put that in
            # the subject
            tag_match = error_log_tag_regex.search(record.msg)
            tag = ''
            if tag_match and tag_match.groups():
                tag = ' ({})'.format(tag_match.groups()[-1])
            
            subject = self.subject + tag

            # Finally send the message!
            if send_email:
                if DEBUG_ERROR_EMAIL_SENDING:
                    log.info('@@@> ! Sending error email to {} !'.format(self.toaddrs))
                send_text_mail(self.toaddrs, subject, msg, self.fromaddr)
            else:
                log.info('!! WARNING: Not sending email as too many emails have been sent in the past minute !!')
                log.info(msg)

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            self.handleError(record)


def init_error_emails(send_error_emails, send_warning_emails, from_address, to_addresses, subject,
                      logger=None, obscured_fields=['password']):
    global _error_reporting_obscured_fields
    
    _error_reporting_obscured_fields = obscured_fields

    if send_error_emails or send_warning_emails:
        log.info('Setting up error / warning emails')
        error_handler = LfsSmtpHandler(from_address, to_addresses, subject)

        if send_warning_emails:
            log.info('Sending WARNING emails as well as ERRORs')
            error_handler.setLevel(logging.WARNING)
        else:
            log.info('Only sending ERROR emails')
            error_handler.setLevel(logging.ERROR)
        
        if logger is None:
            logger = logging.getLogger()

        logger.addHandler(error_handler)
