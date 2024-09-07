import sys
from setuptools import setup

if sys.version_info.major < 3:
    sys.exit('Sorry, this library only supports Python 3')

VERSION = '0.0.1'

setup(
    name='littlefish',
    packages=['littlefish'],
    include_package_data=True,
    version=VERSION,
    description='Flask 3 webapp utility functions by Little Fish Solutions LTD',
    author='Stephen Brown (Little Fish Solutions LTD)',
    author_email='opensource@littlefish.solutions',
    url='https://github.com/stevelittlefish/littlefish3',
    download_url='https://github.com/stevelittlefish/littlefish3/archive/v{}.tar.gz'.format(VERSION),
    keywords=['flask', 'utility', 'time', 'pager'],
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Framework :: Flask',
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries'
    ],
    install_requires=[
        'Flask>=3.0.3',
    ],
    extras_require={
    }
)

