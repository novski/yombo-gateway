"""
Various utilities to help the Yombo Gateway get things done.

.. moduleauthor:: Mitch Schwenk <mitch-gw@yombo.net>

:copyright: Copyright 2016 by Yombo.
:license: LICENSE for details.
"""
# Import python libraries
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    # fcntl is not available on windows
    HAS_FCNTL = False
try:  # Prefer simplejson if installed, otherwise json will work swell.
    import simplejson as json
except ImportError:
    import json
import inspect
import random
import string
import sys
import re
from datetime import datetime
import parsedatetime.parsedatetime as pdt
from struct import pack as struct_pack, unpack as struct_unpack
from socket import inet_aton, inet_ntoa
import math
from time import strftime, localtime, time
import decimal

#from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import deferLater
from twisted.internet import reactor

# Import 3rd-party libs
from yombo.core.exceptions import YomboWarning
from yombo.utils.decorators import memoize_
import yombo.ext.six as six
from yombo.ext.hashids import Hashids

from yombo.core.log import get_logger

logger = get_logger('utils.__init__')


# Import Yombo libraries
from yombo.core.exceptions import YomboNoSuchLoadedComponentError, YomboWarning

def pattern_search(look_for, items):
    """
    Allows searching thru a list of items (a dict or list). For example, a list of:

    ['yombo.status.hello', 'yombo.status.bye', 'visitor.livingroom.hello']

    You can search
    using #'s for whilecards consuming any number of spaces between or +'s as a wildcard for only
    on work.  For example, a search of "#.hello" would result in:

    ['yombo.status.hello', 'visitor.livingroom.hello']

    While a search of "yombo.status.+" would result in:

    ['yombo.status.hello', 'yombo.status.bye']

    :param look_for:
    :param items:
    :return:
    """
    regex = re.compile(look_for.replace('#', '.*').replace('$', '\$').replace('+', '[/\$\s\w\d]+'))
    out_list = []
    if isinstance(items, dict):
        for item, data in items.iteritems():
            result = regex.match(item)
            if result is not None:
                out_list.append(item)
    elif isinstance(items, list):
        for item in items:
            result = regex.match(item)
            if result is not None:
                out_list.append(item)
    return out_list

def epoch_to_string(the_time, format=None):
    if format is None:
        format = '%b %d %Y %H:%M:%S %Z'
    return strftime(format, localtime(the_time))

def epoch_from_string( the_string ):
    """
    Receives a string and parses it into seconds. Some example strings:

    * 1hour - Returns epoch time 1 hour ahead.
    * 1h 3m -3s - Returns epoch 1 hour ahead, but add 3 minutes and subtract 3 seconds
    *

    Inspiration from here:
    http://stackoverflow.com/questions/1810432/handling-the-different-results-from-parsedatetime

    :param s:
    :return:
    """
    c = pdt.Calendar()
    result, what = c.parse( the_string )

    dt = None

    # what was returned (see http://code-bear.com/code/parsedatetime/docs/)
    # 0 = failed to parse
    # 1 = date (with current time, as a struct_time)
    # 2 = time (with current date, as a struct_time)
    # 3 = datetime
    if what in (1,2):
        # result is struct_time
        dt = datetime( *result[:6] )
    elif what == 3:
        # result is a datetime
        dt = result

    if dt is None:
        # Failed to parse
        raise YomboWarning("Cannot parse this string into a date: '"+the_string+"'", 101, "epoch_from_string", 'utils')
    return int(dt.strftime('%s'))

def convert_to_seconds(s):
    seconds_per_unit = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    return int(s[:-1]) * seconds_per_unit[s[-1]]

def split(the_string, delimiter=','):
    """
    Pass in a string, and get back a list. This also ignore white spaces padding the delimiter.

    :param the_string: The string to parse
    :param delimiter: Default: , (commad).
    :return:
    """
    return [x.strip() for x in the_string.split(',')]

def string_to_number(input):
    try:
        return int(input)
    except ValueError:
        return float(input)

def clean_kwargs(**kwargs):
    """
    Returns a dictionary without any keys starting with "__" (double underscore).
    """
    data = {}
    start = kwargs.get('start', '__')
    for key, val in six.iteritems(kwargs):
        if not key.startswith(start):
            data[key] = val
    return data

def clean_dict(dictionary, **kwargs):
    """
    Returns a dictionary without any keys starting with kwargs['start'] (default '_' underscore).
    """
    data = {}
    start = kwargs.get('start', '_')
    for key, val in six.iteritems(dictionary):
        if not key.startswith(start):
            data[key] = val
    return data

def dict_has_key(dictionary, keys):
    """
    Check if a dictionary has the given list of keys

    **Usage**:

    .. code-block:: python

       from yombo.utils import dict_has_key
       a_dictionary = {'identity': {'location': {'state': 'California'}}}
       a_list = ['identity', 'location', 'state']
       has_state = dict_has_key(a_dictionary, a_list)
       #has_state is now: True

    :param dictionary: A dictionary to check
    :type dictionary: dict
    :param key: A list of keys
    :type key: list
    """
    if not isinstance(keys, list):
        keys = [keys]
    try:
        for key in keys:
             tossaway = dictionary[key]
    except KeyError:
        return False
    except TypeError:
        return False
    else:
        return True

def dict_find_key(symbol_dic, val):
    """
    Find a key of a dictionary for a given key.

    :param symbol_dic: The dictionary to search.
    :type symbol_dic: dict
    :param val: The value to search for.
    :type val: any valid dict key type
    :return: The key of dictionary dic given the value
    :rtype: any valid dict key type
    """
    return [k for k, v in symbol_dic.iteritems() if v == val][0]

def dict_has_value(dictionary, keys, value):
    """
    Check if a dictionary has the value based on a given list of keys

    **Usage**:

    .. code-block:: python

       from yombo.utils import dict_has_value
       a_dictionary = {'identity': {'location': {'state': 'California'}}}
       a_list = ['identity', 'location', 'state']
       has_california = dict_has_value(a_dictionary, a_list, 'California')
       #has_california is now: True

    :param dictionary: A dictionary to check
    :type dictionary: dict
    :param key: A list of keys
    :type key: list
    :param value: The value to test for
    :type value: Any value a dictionary can hold.
    """
    if not isinstance(keys, list):
        keys = [keys]
    try:
        for key in keys[:-1]:
             dictionary = dictionary[key]
        if dictionary[keys[-1]] == value:
            return True
    except KeyError:
        return False
    except TypeError:
        return False
    else:
        return False

def dict_set_value(dictionary, keys, value):
    """
    Set dictionary value based on a given list of keys

    **Usage**:

    .. code-block:: python

       from yombo.utils import dict_set_value
       a_dictionary = {}
       a_list = ['identity', 'location', 'state']
       dict_set_value(a_dictionary, a_list, 'California')
       #a_dictionary now: {'identity': {'location': {'state': 'California'}}}

    :param dictionary: A dictionary to update
    :type dictionary: dict
    :param key: A list of keys
    :type key: list
    :param value: The value to set
    :type value: Any value a dictionary can hold.
    """
    if not isinstance(keys, list):
        keys = [keys]
    for key in keys[:-1]:
         dictionary = dictionary.setdefault(key, {})
    dictionary[keys[-1]] = value

def dict_get_value(dictionary, keys):
    """
    Get dictionary value based on a given list of keys

    **Usage**:

    .. code-block:: python

       from yombo.utils import dict_get_value
       a_dictionary  = {'identity': {'location': {'state': 'California'}}}
       a_list = ['identity', 'location', 'state']
       value = dict_get_value(a_dictionary, a_list)
       #value = 'California'

    :param dictionary: A dictionary to update
    :type dictionary: dict
    :param key: A list of keys
    :type key: list
    """
    if not isinstance(keys, list):
        keys = [keys]
    for key in keys[:-1]:
         dictionary = dictionary.setdefault(key, {})
    return dictionary[keys[-1]]

def dict_merge(original, changes):
    """
    Recursively merges a dictionary with any changes. Sub-dictionaries won't be overwritten - just updated.

    *Usage**:

    .. code-block:: python

        my_information = {
            'name': 'Mitch'
            'phone: {
                'mobile': '4155551212'
            }
        }

        updated_information = {
            'phone': {
                'home': '4155552121'
            }
        }

        print dict_merge(my_information, updated_information)

    # Output:

    .. code-block:: none

        {
            'name': 'Mitch'
            'phone: {
                'mobile': '4155551212',
                'home': '4155552121'
            }
        }
    """
    for key, value in original.iteritems():
        if key not in changes:
            changes[key] = value
        elif isinstance(value, dict):
            dict_merge(value, changes[key])
    return changes

def fopen(*args, **kwargs):
    """
    A help function that wraps around python open() function. Makes handling files a across platforms easier.

    Modules that are looking to keep files open for reading, such as file monitoring, should use the the
    :py:mod:`yombo.utils.filereader` class.
    """
    # For windows, always use binary mode.
    if kwargs.pop('binary', True):
        if is_windows():
            if len(args) > 1:
                args = list(args)
                if 'b' not in args[1]:
                    args[1] += 'b'
            elif kwargs.get('mode', None):
                if 'b' not in kwargs['mode']:
                    kwargs['mode'] += 'b'
            else:
                # the default is to read
                kwargs['mode'] = 'rb'

    fhandle = open(*args, **kwargs)
    if is_fcntl_available():
        # modify the file descriptor on systems with fcntl
        # unix and unix-like systems only
        try:
            FD_CLOEXEC = fcntl.FD_CLOEXEC   # pylint: disable=C0103
        except AttributeError:
            FD_CLOEXEC = 1                  # pylint: disable=C0103
        old_flags = fcntl.fcntl(fhandle.fileno(), fcntl.F_GETFD)
        fcntl.fcntl(fhandle.fileno(), fcntl.F_SETFD, old_flags | FD_CLOEXEC)
    return fhandle

def percentage(part, whole):
    """
    Return a float representing a percentage of part against the whole.

    For example: percentage(7, 12) returns: 58.333333333333336

    :param part:
    :param whole:
    :return:
    """
    return 100 * float(part)/float(whole)

def percentile(data_list, percent, key=lambda x:x):
    """
    Find the percentile of a list of values.

    I think this was found here:http://code.activestate.com/recipes/511478-finding-the-percentile-of-the-values/

    :param data_list: A list of values. Note N MUST BE already sorted.
    :param percent: A float value from 0.0 to 1.0.
    :param key: Optional key function to compute value from each element of N

    :return: The percentile of the values
    """
    if not data_list:
        return None
    k = (len(data_list)-1) * percent
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return key(data_list[int(k)])
    d0 = key(data_list[int(f)]) * (c-k)
    d1 = key(data_list[int(c)]) * (k-f)
    return d0+d1

def get_command(commandSearch):
    """
    Returns a pointer to a command.

    .. note::

       This shouldn't be used by modules, instead, use the pre-defined pointer
       *self._Commands*, see: :py:func:`get_commands`.

    :param commandSearch: Search for a given command, by cmdUUID or label. cmdUUID is preferred.
    :type commandSearch: string - Command UUID or Command Label.
    :return: The pointer to a single command.
    :rtype: object
    """
    return get_command('yombo.gateway.lib.commands')._search(commandSearch)

def get_method_definition_level(meth):
    for cls in inspect.getmro(meth.im_class):
        if meth.__name__ in cls.__dict__: return str(cls)
    return None

def get_local_ip_address():
    """
    Get the ip address of the local machine.


    No single/simple way to do this.  First, do a simple get (works on windows).
    Then if that doesn't work, use the hostname -I function of the os.

    #@TODO: The second method needs to be fixed. Needs to prompt or something
    """
    import socket
    addr = socket.gethostbyname(socket.gethostname())

    badips = ['127.0.0.1', '127.0.1.1']

    if addr in badips:
       import commands
       addr = commands.getoutput("hostname -I")

    addr = addr.split()
    addr = addr[0]
    return addr.strip()

def get_external_ip_address():
    """
    Get the IP address of this machine as seen from the outside world.  THis
    function is primarily used during various internal testing of the Yombo
    Gateway.  This information is reported to the Yombo Service, however, the
    Yombo Service already knows you're IP address during the process of
    downloading configuration files.

    Yombo servers will only use this information if server "getpeer.ip()" function
    results in a private IP address.  See: http://en.wikipedia.org/wiki/Private_network
    This assists in Yombo performing various tests internally, but still providing
    an ability to do further tests.

    Gives Yombo servers a hint of your external ip address from your view. This
    should be the same as what Yombo servers see when you connect.

    This is called only once during the startup phase.  Calling this function too
    often can result in the gateway being blocked by whatismyip.org

    .. warning::

       This is 100% blocking code. A replacement will be coming soon.

    :return: An ip address
    :rtype: string
    """
    import urllib3
    urllib3.disable_warnings()  # just getting client IP address from outside view. Not a big issue here.
    http = urllib3.PoolManager()
    r = http.request("GET", "https://yombo.net/tools/clientip.php")
    return r.data.strip()

def ip_address_to_int(address):
    return struct_unpack("!I", inet_aton(address))[0]

def int_to_ip_address(address):
    return inet_ntoa(struct_pack("!I", address))

def random_string(**kwargs):
    """
    Generate a random alphanumeric string. *All arguments are kwargs*.

    **Usage**:

    .. code-block:: python

       from yombo.utils import random_string
       someRandonness = random_string(letters="abcdef0123456") #make a hex value

    :param length: Length of the output string. Default: 32
    :type length: int
    :param letters: A string of characters to to create the new string from.
        Default: letters upper and lower, numbers 0-9
    :type letters: string
    :return: A random string that contains choices from `letters`.
    :rtype: string
    """
    length = kwargs.get('length', 32)
    letters = kwargs.get('letters', None)

    if not hasattr(random_string, 'randomStuff'):
        random_string.randomStuff = random.SystemRandom()

    if letters is None:
        lst = [random_string.randomStuff.choice(string.ascii_letters + string.digits) for n in xrange(length)]
        return "".join(lst)
    else:
        lst = [random_string.randomStuff.choice(letters) for n in xrange(length)]
        return "".join(lst)

def human_alpabet():
    return "ABCDEFGHJKLMNPQRTSUVWXYZabcdefghkmnopqrstuvwxyz23456789"

def pretty_date(time=False):
    """
    Source: http://stackoverflow.com/questions/1551382/user-friendly-time-format-in-python

    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    from datetime import datetime
    now = datetime.now()
    if type(time) is float:
        time = int(round(time))
    if type(time) is int:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time,datetime):
        diff = now - time
    elif not time:
        diff = now - now
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ''

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(second_diff) + " seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return str(second_diff / 60) + " minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str(second_diff / 3600) + " hours ago"
    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(day_diff / 7) + " weeks ago"
    if day_diff < 365:
        return str(day_diff / 30) + " months ago"
    return str(day_diff / 365) + " years ago"

def generate_uuid(**kwargs):
    """
    Create a 30 character UUID, where only 26 of the characters are random.
    The remaining 4 characters are used by developers to track where a
    UUID originated from.

    **All arguments are kwargs.**

    **Usage**:

    .. code-block:: python

       from yombo.utils import generate_uuid
       newUUID = generate_uuid(maintype='G', subtype='a2A')

    :param maintype: A single alphanumeric (0-9, a-z, A-Z) to note the uuid main type.
    :type maintype: char
    :param maintype: Up to 3 characters (0-9, a-z, A-Z) to note the uuid sub type.
    :type subtype: string
    :return: A random string, with source identifiers at the end, 30 bytes in length.
    :rtype: string
    """
    uuid = random_string(length=26)
    maintype= kwargs.get('maintype', 'z')
    subtype= kwargs.get('subtype', 'zzz')

    okPattern = re.compile(r'([0-9a-zA-Z]+)')

    m = re.search(okPattern, maintype)
    if m:
        pass
    else:
        maintype = "z"
        subtype = "zzz"

    m = re.search(okPattern, subtype)
    if m:
        pass
    else:
        subtype = "zzz"

    if len(maintype) != 1:
        type = "z";

    if len(subtype) == 1:
        subtype = "zz" + subtype
    elif len(subtype) == 2:
        subtype = "z" + subtype
    elif len(subtype) == 3:
        pass
    else:
        subtype = "zzz"

    tempit = uuid + subtype + maintype
    return tempit

def global_invoke_all(hook, **kwargs):
    """
    Call all hooks in libraries and modules. Basically a shortcut for calling module_invoke_all and libraries_invoke_all
    methods.

    :param hook: The hook name to call.
    :param kwargs: kwargs to send to the function.
    :return: a dictionary of results.
    """
    lib_results = get_component('yombo.gateway.lib.loader').library_invoke_all(hook, True, **kwargs)
    modules_results = get_component('yombo.gateway.lib.modules').module_invoke_all(hook, True, **kwargs)
    return dict_merge(modules_results, lib_results)

def get_component(name):
    """
    Return loaded component (module or library). This can be used to find
    other modules or libraries. The getComponent uses the :ref:`FuzzySearch <fuzzysearch>`
    class to make searching easier, but can only be off one or two letters
    due to importance of selecting the correct library or module.

    :raises YomboNoSuchLoadedComponentError: When the requested component cannot be found.
    :param name: The name of the component (library or module) to find.  Returns a
        pointer to the object so it's functions and attributes can be accessed.
    :type name: string
    :return: Pointer to requested library or module.
    :rtype: Object reference
    """
    if not hasattr(get_component, 'components'):
        from yombo.lib.loader import get_the_loaded_components
        get_component.components = get_the_loaded_components()
    try:
        return get_component.components[name.lower()]
    except KeyError:
        raise YomboNoSuchLoadedComponentError("No such loaded component:" + str(name))

def is_string_bool(value=None):
    """
    Returns a True/False/None based on the string. If nothing is found, "YomboWarning" is raised.
    Returns a boolean value representing the "truth" of the value passed. Returns true if the string
    provided is 'true/True/trUE, etc'.

    :param value: String of either "true" or "false" (case insensitive), returns bool or raises YomboWarning.
    """
    if isinstance(value, six.string_types):
        if str(value).lower() == 'true':
            return True
        elif str(value).lower() == 'false':
            return False
        elif str(value).lower() == 'none':
            return None
    raise YomboWarning("String is not true, false, or none.")

def is_true_false(input, only_bool=False):
    """
    Used by various utils to determine if an input is high or low. Other functions like is_one_zero and is_yes_no will
    return the results in different ways based on results from here

    :param input: A string, bool, int to test
    :param only_bool: If true, will only return bools. Otherwise, None will be returned if indeterminate input.
    :return:
    """
    if isinstance(input, bool):
            return input
    elif isinstance(input, six.string_types):
        input = input.lower()
        if input in ("true", "1", "open", "on", "running"):
            return True
        if input in ("false", "0", "closed", "off", "stopped"):
            return False
    elif isinstance(input, six.integer_types):
            if input == 1:
                return True
            elif input == 0:
                return False
    else:
        if only_bool:
            return False
        else:
            return None

def is_yes_no(input):
    """
    Tries to guess if input is a positive value (1, "1", True, "On", etc). If it is, returns "Yes", otherwise,
    returns "No". Useful to convert something to human Yes/No.
    :param input:
    :return: String on either "Yes" or "No".
    """
    if is_true_false(input, True):
        return "Yes"
    else:
        return "No"

def is_one_zero(input):
    """
    Like is_yes_no, but returns 1 for yes/true/on/open/running, 0 for otherwise.

    Tries to guess if input is a positive value (1, "1", True, "On", etc). If it is, returns "Yes", otherwise,
    returns "No". Useful to convert something to human Yes/No.
    :param input:
    :return:
    """
    if is_true_false(input, True):
        return 1
    else:
        return 0

def test_bit(int_type, offset):
    """
    Tests wether a specific bit is on or off for a given int.

    :param int_type: The given int to interrogate.
    :type int_type: int
    :param offset: The bit location to return, starting from lowest to highest.
    :type offset: int
    :return: If the bit is on or off
    """
    mask = 1 << offset
    if (int_type & mask) > 0:
      return 1
    else:
      return 0
    return(int_type & mask)

class ViewAsObject(object):
    def __init__(self, d):
        self.__dict__ = d

def sleep(secs):
    """
    A simple non-blocking sleep function.  This generates a twisted
    deferred. You have to decorate your function to make the yield work
    properly.

    **Usage**:

    .. code-block:: python

       from twisted.internet import defer
       from yombo.core.helpers import sleep

       @defer.inlineCallbacks
       def myFunction(self):
           logger.info("About to sleep.")
           yield sleep(5.4) # sleep 5.4 seconds.
           logger.info("I'm refreshed.")

    :param secs: Number of seconds (whole or partial) to sleep for.
    :type secs: int of float
    """
    return deferLater(reactor, secs, lambda: None)

def hashid_encode(input, min_length=2, salt='', alphabet='ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvxyz234'):
    """
    Encodes an int and returns a string. This typically shortens the length and is great for
    showing users a better representation of a large int - if they don't care about the actual value.

    :param input: Int - Input value to encode to a string.
    :param min_length: Int - Minimum length string should be. Will pad if required.
    :param salt: String - A salt to mangle the value. This isn't secure!
    :param alphabet: String -
    :return:
    """
    hashid = Hashids(salt, min_length, alphabet)
    return hashid.encode(input)

def hashid_decode(input, min_length=2, salt='', alphabet='ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvxyz234'):
    hashid = Hashids(salt, min_length, alphabet)
    return hashid.decode(input)

# basic conversions

unit_converters = {
    'km_mi': lambda x: x*0.62137119,  # miles
    'mi_km': lambda x: x*1.6093,  # kilometers
    'm_ft': lambda x: x*3.28084,  # feet
    'ft_m': lambda x: x*0.3048,  # meters
    'cm_in': lambda x: x*0.39370079,  # inches
    'in_cm': lambda x: x*2.54,  # inches
    'oz_g': lambda x: x*28.34952,  # grams
    'g_oz': lambda x: x*0.03527396195,  # ounces
    'kg_lb': lambda x: x*2.20462262185,  # pounds
    'lb_kg': lambda x: x*0.45359237,  # pounds
    'f_c': lambda x: float((x - 32) * (5.0/9.0)),  # celsius
    'c_f': lambda x: float((9.0/5.0) * (x + 32)),  # fahrenheit
    'btu_kwh': lambda x: x*0.00029307107017,  # kilowatt-hour
    'kwh_btu': lambda x: x*3412.14163312794,  # btu
}

def unit_convert(unit_type, unit_size):
    """
    Converst various types of lenghts, masses, and temperatures. The format of the list below is: (from)_(to)
    For example, "g_oz" converts from grams to ounces.

    Usage: yombo.utils.unit_convert('km_mi', 10)  # returns 10 km in miles.

    Valid unit_types:
    'km_mi' - kilometers to miles
    'mi_km' - miles to kilometers
    'm_ft' - meters to feet
    'ft_m' - feet to meters
    'cm_in' - centimeter to inches
    'in_cm' - inches to centimeters
    'oz_g' - ounces to grames
    'g_oz' - grames to ounces
    'kg_lb' - kilograms to pounds
    'lb_kg' - pounts to kilograms
    'f_c' - fahrenheit to celsius
    'c_f' - celsius to fahrenheit
    'btu_kwh' - btu's to kilowatt-hours
    'kwh_btu' - kilowatt-hours to btu's

    :param unit_type: string - unit types to convert from_to
    :param unit_size: int or float - value to convert
    :return: float - converted unit
    """
    return unit_converters[unit_type](unit_size)

def is_json(myjson):
    """
    Helper function to determine if data is json or not.

    :param myjson:
    :return:
    """
    try:
        json_object = json.loads(myjson)
    except:
        return False
    return True

def is_msgpack(mymsgpack):
    """
    Helper function to determine if data is msgpack or not.

    :param mymsgpack:
    :return:
    """
    try:
        json_object = msgpack.loads(mymsgpack)
    except:
        return False
    return True

@memoize_
def is_freebsd():
    """
    Returns if the host is freebsd or not
    """
    return sys.platform.startswith('freebsd')

@memoize_
def is_linux():
    """
    Returns if the host is linus or not
    """
    return sys.platform.startswith('linux')

@memoize_
def is_windows():
    """
    Returns if the host is windows or not
    """
    return sys.platform.startswith('win')

@memoize_
def is_sunos():
    """
    Returns if the host is sunos or not
    """
    return sys.platform.startswith('sunos')

@memoize_
def is_fcntl_available(check_sunos=False):
    """
    Simple function to check if the `fcntl` module is available or not.

    If `check_sunos` is passed as `True` an additional check to see if host is
    SunOS is also made.
    """
    if check_sunos and is_sunos():
        return False
    return HAS_FCNTL
