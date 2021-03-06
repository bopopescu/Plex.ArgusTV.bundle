# MySQL Connector/Python - MySQL driver written in Python.
# Copyright (c) 2009, 2014, Oracle and/or its affiliates. All rights reserved.

# MySQL Connector/Python is licensed under the terms of the GPLv2
# <http://www.gnu.org/licenses/old-licenses/gpl-2.0.html>, like most
# MySQL Connectors. There are special exceptions to the terms and
# conditions of the GPLv2 as it is applied to this software, see the
# FOSS License Exception
# <http://www.mysql.com/about/legal/licensing/foss-exception.html>.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA

"""Converting MySQL and Python types
"""

import struct
import datetime
import time
from decimal import Decimal

from mysql.connector.constants import FieldType, FieldFlag, CharacterSet


class HexLiteral(str):

    """Class holding MySQL hex literals"""
    def __new__(cls, str_, charset='utf8'):
        hexed = ["{0:x}".format(ord(i)) for i in str_.encode(charset)]
        obj = str.__new__(cls, ''.join(hexed))
        obj.charset = charset
        obj.original = str_
        return obj

    def __str__(self):
        return '0x' + self


class MySQLConverterBase(object):
    """Base class for conversion classes

    All class dealing with converting to and from MySQL data types must
    be a subclass of this class.
    """
    def __init__(self, charset='utf8', use_unicode=True):
        self.python_types = None
        self.mysql_types = None
        self.charset = None
        self.charset_id = 0
        self.use_unicode = None
        self.set_charset(charset)
        self.set_unicode(use_unicode)

    def set_charset(self, charset):
        """Set character set"""
        if charset == 'utf8mb4':
            charset = 'utf8'
        if charset is not None:
            self.charset = charset
        else:
            # default to utf8
            self.charset = 'utf8'
        self.charset_id = CharacterSet.get_charset_info(self.charset)[0]

    def set_unicode(self, value=True):
        """Set whether to use Unicode"""
        self.use_unicode = value

    def to_mysql(self, value):
        """Convert Python data type to MySQL"""
        return value

    def to_python(self, vtype, value):
        """Convert MySQL data type to Python"""
        return value

    def escape(self, buf):
        """Escape buffer for sending to MySQL"""
        return buf

    def quote(self, buf):
        """Quote buffer for sending to MySQL"""
        return str(buf)


class MySQLConverter(MySQLConverterBase):
    """Default conversion class for MySQL Connector/Python.
     o escape method: for escaping values send to MySQL
     o quoting method: for quoting values send to MySQL in statements
     o conversion mapping: maps Python and MySQL data types to
       function for converting them.

    Whenever one needs to convert values differently, a converter_class
    argument can be given while instantiating a new connection like
    cnx.connect(converter_class=CustomMySQLConverterClass).

    """
    def __init__(self, charset=None, use_unicode=True):
        MySQLConverterBase.__init__(self, charset, use_unicode)
        self._cache_field_types = {}

    def escape(self, value):
        """
        Escapes special characters as they are expected to by when MySQL
        receives them.
        As found in MySQL source mysys/charset.c

        Returns the value if not a string, or the escaped string.
        """
        if value is None:
            return value
        elif isinstance(value, (int, float, long, Decimal, HexLiteral)):
            return value
        res = value
        res = res.replace('\\', '\\\\')
        res = res.replace('\n', '\\n')
        res = res.replace('\r', '\\r')
        res = res.replace('\047', '\134\047')  # single quotes
        res = res.replace('\042', '\134\042')  # double quotes
        res = res.replace('\032', '\134\032')  # for Win32
        return res

    def quote(self, buf):
        """
        Quote the parameters for commands. General rules:
          o numbers are returns as str type (because operation expect it)
          o None is returned as str('NULL')
          o String are quoted with single quotes '<string>'

        Returns a string.
        """
        if isinstance(buf, (int, long, Decimal, HexLiteral)):
            return str(buf)
        elif isinstance(buf, float):
            return repr(buf)
        elif isinstance(buf, type(None)):
            return "NULL"
        else:
            # Anything else would be a string
            return "'%s'" % buf

    def to_mysql(self, value):
        """Convert Python data type to MySQL"""
        type_name = value.__class__.__name__.lower()
        try:
            return getattr(self, "_%s_to_mysql" % str(type_name))(value)
        except AttributeError:
            raise TypeError("Python '{0}' cannot be converted to a "
                            "MySQL type".format(type_name))

    def _int_to_mysql(self, value):
        """Convert value to int"""
        return int(value)

    def _long_to_mysql(self, value):
        """Convert value to long"""
        return long(value)

    def _float_to_mysql(self, value):
        """Convert value to float"""
        return float(value)

    def _str_to_mysql(self, value):
        """Convert value to string"""
        return str(value)

    def _unicode_to_mysql(self, value):
        """
        Encodes value, a Python unicode string, to whatever the
        character set for this converter is set too.
        """
        encoded = value.encode(self.charset)
        if self.charset_id in CharacterSet.slash_charsets:
            if '\x5c' in encoded:
                return HexLiteral(value, self.charset)
        return encoded

    def _bool_to_mysql(self, value):
        """Convert value to boolean"""
        if value:
            return 1
        else:
            return 0

    def _nonetype_to_mysql(self, value):
        """
        This would return what None would be in MySQL, but instead we
        leave it None and return it right away. The actual conversion
        from None to NULL happens in the quoting functionality.

        Return None.
        """
        return None

    def _datetime_to_mysql(self, value):
        """
        Converts a datetime instance to a string suitable for MySQL.
        The returned string has format: %Y-%m-%d %H:%M:%S[.%f]

        If the instance isn't a datetime.datetime type, it return None.

        Returns a string.
        """
        if value.microsecond:
            return '%d-%02d-%02d %02d:%02d:%02d.%06d' % (
                value.year, value.month, value.day,
                value.hour, value.minute, value.second,
                value.microsecond)
        return '%d-%02d-%02d %02d:%02d:%02d' % (
            value.year, value.month, value.day,
            value.hour, value.minute, value.second)

    def _date_to_mysql(self, value):
        """
        Converts a date instance to a string suitable for MySQL.
        The returned string has format: %Y-%m-%d

        If the instance isn't a datetime.date type, it return None.

        Returns a string.
        """
        return '%d-%02d-%02d' % (value.year, value.month, value.day)

    def _time_to_mysql(self, value):
        """
        Converts a time instance to a string suitable for MySQL.
        The returned string has format: %H:%M:%S[.%f]

        If the instance isn't a datetime.time type, it return None.

        Returns a string or None when not valid.
        """
        if value.microsecond:
            return value.strftime('%H:%M:%S.%%06d') % value.microsecond
        return value.strftime('%H:%M:%S')

    def _struct_time_to_mysql(self, value):
        """
        Converts a time.struct_time sequence to a string suitable
        for MySQL.
        The returned string has format: %Y-%m-%d %H:%M:%S

        Returns a string or None when not valid.
        """
        return time.strftime('%Y-%m-%d %H:%M:%S', value)

    def _timedelta_to_mysql(self, value):
        """
        Converts a timedelta instance to a string suitable for MySQL.
        The returned string has format: %H:%M:%S

        Returns a string.
        """
        seconds = abs(value.days * 86400 + value.seconds)

        if value.microseconds:
            fmt = '{0:02d}:{1:02d}:{2:02d}.{3:06d}'
            if value.days < 0:
                mcs = 1000000 - value.microseconds
                seconds -= 1
            else:
                mcs = value.microseconds
        else:
            fmt = '{0:02d}:{1:02d}:{2:02d}'

        if value.days < 0:
            fmt = '-' + fmt

        (hours, remainder) = divmod(seconds, 3600)
        (mins, secs) = divmod(remainder, 60)

        if value.microseconds:
            return fmt.format(hours, mins, secs, mcs)
        return fmt.format(hours, mins, secs)

    def _decimal_to_mysql(self, value):
        """
        Converts a decimal.Decimal instance to a string suitable for
        MySQL.

        Returns a string or None when not valid.
        """
        if isinstance(value, Decimal):
            return str(value)

        return None

    def to_python(self, flddsc, value):
        """
        Converts a given value coming from MySQL to a certain type in Python.
        The flddsc contains additional information for the field in the
        table. It's an element from MySQLCursor.description.

        Returns a mixed value.
        """
        if value == '\x00' and flddsc[1] != FieldType.BIT:
            # Don't go further when we hit a NULL value
            return None
        if value is None:
            return None

        if not self._cache_field_types:
            self._cache_field_types = {}
            for name, info in FieldType.desc.items():
                try:
                    self._cache_field_types[info[0]] = getattr(
                        self, '_{0}_to_python'.format(name))
                except AttributeError:
                    # We ignore field types which has no method
                    pass

        try:
            return self._cache_field_types[flddsc[1]](value, flddsc)
        except KeyError:
            # If one type is not defined, we just return the value as str
            return str(value)
        except ValueError as err:
            raise ValueError("%s (field %s)" % (err, flddsc[0]))
        except TypeError as err:
            raise TypeError("%s (field %s)" % (err, flddsc[0]))
        except:
            raise

    def _FLOAT_to_python(self, value, desc=None):  # pylint: disable=C0103
        """
        Returns value as float type.
        """
        return float(value)
    _DOUBLE_to_python = _FLOAT_to_python

    def _INT_to_python(self, value, desc=None):  # pylint: disable=C0103
        """
        Returns value as int type.
        """
        return int(value)
    _TINY_to_python = _INT_to_python
    _SHORT_to_python = _INT_to_python
    _INT24_to_python = _INT_to_python

    def _LONG_to_python(self, value, desc=None):  # pylint: disable=C0103
        """
        Returns value as long type.
        """
        return int(value)
    _LONGLONG_to_python = _LONG_to_python

    def _DECIMAL_to_python(self, value, desc=None):  # pylint: disable=C0103
        """
        Returns value as a decimal.Decimal.
        """
        return Decimal(value)
    _NEWDECIMAL_to_python = _DECIMAL_to_python

    def _str(self, value, desc=None):
        """
        Returns value as str type.
        """
        return str(value)

    def _BIT_to_python(self, value, dsc=None):  # pylint: disable=C0103
        """Returns BIT columntype as integer"""
        int_val = value
        if len(int_val) < 8:
            int_val = '\x00' * (8-len(int_val)) + int_val
        return struct.unpack('>Q', int_val)[0]

    def _DATE_to_python(self, value, dsc=None):  # pylint: disable=C0103
        """
        Returns DATE column type as datetime.date type.
        """
        try:
            parts = value.split('-')
            return datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None
    _NEWDATE_to_python = _DATE_to_python

    def _TIME_to_python(self, value, dsc=None):  # pylint: disable=C0103
        """
        Returns TIME column type as datetime.timedelta type.
        """
        time_val = None
        try:
            (hms, mcs) = value.split('.')
            mcs = int(mcs.ljust(6, '0'))
        except ValueError:
            hms = value
            mcs = 0
        try:
            (hours, mins, secs) = [int(d) for d in hms.split(':')]
            if value[0] == '-':
                mins, secs, mcs = -mins, -secs, -mcs
            time_val = datetime.timedelta(hours=hours, minutes=mins,
                                          seconds=secs, microseconds=mcs)
        except ValueError:
            raise ValueError(
                "Could not convert %s to python datetime.timedelta" % value)
        else:
            return time_val

    def _DATETIME_to_python(self, value, dsc=None):  # pylint: disable=C0103
        """
        Returns DATETIME column type as datetime.datetime type.
        """
        datetime_val = None
        try:
            (date_, time_) = value.split(' ')
            if len(time_) > 8:
                (hms, mcs) = time_.split('.')
                mcs = int(mcs.ljust(6, '0'))
            else:
                hms = time_
                mcs = 0
            dtval = [int(value) for value in date_.split('-')] +\
                 [int(value) for value in hms.split(':')] + [mcs,]
            datetime_val = datetime.datetime(*dtval)
        except ValueError:
            datetime_val = None

        return datetime_val
    _TIMESTAMP_to_python = _DATETIME_to_python

    def _YEAR_to_python(self, value, desc=None):  # pylint: disable=C0103
        """Returns YEAR column type as integer"""
        try:
            year = int(value)
        except ValueError:
            raise ValueError("Failed converting YEAR to int (%s)" % value)

        return year

    def _SET_to_python(self, value, dsc=None):  # pylint: disable=C0103
        """Returns SET column typs as set

        Actually, MySQL protocol sees a SET as a string type field. So this
        code isn't called directly, but used by STRING_to_python() method.

        Returns SET column type as a set.
        """
        set_type = None
        try:
            set_type = set(value.split(','))
        except ValueError:
            raise ValueError("Could not convert SET %s to a set." % value)
        return set_type

    def _STRING_to_python(self, value, dsc=None):  # pylint: disable=C0103
        """
        Note that a SET is a string too, but using the FieldFlag we can see
        whether we have to split it.

        Returns string typed columns as string type.
        """
        if dsc is not None:
            # Check if we deal with a SET
            if dsc[7] & FieldFlag.SET:
                return self._SET_to_python(value, dsc)
            if dsc[7] & FieldFlag.BINARY:
                return value

        if self.use_unicode:
            try:
                return unicode(value, self.charset)
            except:
                raise

        return str(value)
    _VAR_STRING_to_python = _STRING_to_python

    def _BLOB_to_python(self, value, dsc=None):  # pylint: disable=C0103
        """Convert BLOB data type to Python"""
        if dsc is not None:
            if dsc[7] & FieldFlag.BINARY:
                return value

        return self._STRING_to_python(value, dsc)
    _LONG_BLOB_to_python = _BLOB_to_python
    _MEDIUM_BLOB_to_python = _BLOB_to_python
    _TINY_BLOB_to_python = _BLOB_to_python
