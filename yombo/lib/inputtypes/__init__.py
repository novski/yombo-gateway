# This file was created by Yombo for use with Yombo Python Gateway automation
# software.  Details can be found at https://yombo.net
"""

.. note::

  For more information see: `Input Type @ Module Development <https://yombo.net/docs/libraries/input_types>`_

This library maintains a list of all available input types. The input types (plural) is a wrapper class and contains all
the individual input type classes.

The input type (singular) class represents one input type.

.. moduleauthor:: Mitch Schwenk <mitch-gw@yombo.net>
.. versionadded:: 0.12.0

:copyright: Copyright 2016-2017 by Yombo.
:license: LICENSE for details.
:view-source: `View Source Code <https://yombo.net/Docs/gateway/html/current/_modules/yombo/lib/inputtypes.html>`_
"""
from functools import partial
from time import time

# Import twisted libraries
from twisted.internet.defer import inlineCallbacks, Deferred

# Import Yombo libraries
from yombo.core.exceptions import YomboWarning
from yombo.core.library import YomboLibrary
from yombo.core.log import get_logger
from yombo.utils import search_instance, do_search_instance, global_invoke_all
import collections
from functools import reduce
logger = get_logger('library.inputtypes')

BASE_VALIDATORS = [
    ['yombo.lib.inputtypes.automation_addresses', 'X10_Address'],
    ['yombo.lib.inputtypes.automation_addresses', 'X10_House'],
    ['yombo.lib.inputtypes.automation_addresses', 'X10_Unit'],
    ['yombo.lib.inputtypes.automation_addresses', 'Insteon_Address'],
    ['yombo.lib.inputtypes.basic_addresses', 'Email'],
    ['yombo.lib.inputtypes.basic_addresses', 'YomboUsername'],
    ['yombo.lib.inputtypes.basic_addresses', 'URI'],
    ['yombo.lib.inputtypes.basic_addresses', 'URL'],
    ['yombo.lib.inputtypes.basic_types', '_Any'],
    ['yombo.lib.inputtypes.basic_types', '_Bool'],
    ['yombo.lib.inputtypes.basic_types', '_Checkbox'],
    ['yombo.lib.inputtypes.basic_types', '_Float'],
    ['yombo.lib.inputtypes.basic_types', 'Filename'],
    ['yombo.lib.inputtypes.basic_types', '_Integer'],
    ['yombo.lib.inputtypes.basic_types', '_None'],
    ['yombo.lib.inputtypes.basic_types', 'Number'],
    ['yombo.lib.inputtypes.basic_types', 'Password'],
    ['yombo.lib.inputtypes.basic_types', 'Percent'],
    ['yombo.lib.inputtypes.basic_types', '_String'],
    ['yombo.lib.inputtypes.ip_address', 'IP_Address'],
    ['yombo.lib.inputtypes.ip_address', 'IP_Address_Public'],
    ['yombo.lib.inputtypes.ip_address', 'IP_Address_Private'],
    ['yombo.lib.inputtypes.ip_address', 'IPv4_Address'],
    ['yombo.lib.inputtypes.ip_address', 'IPv4_Address_Public'],
    ['yombo.lib.inputtypes.ip_address', 'IPv4_Address_Private'],
    ['yombo.lib.inputtypes.ip_address', 'IPv6_Address'],
    ['yombo.lib.inputtypes.ip_address', 'IPv6_Address_Public'],
    ['yombo.lib.inputtypes.ip_address', 'IPv6_Address_Private'],
    ['yombo.lib.inputtypes.latin_alphabet', 'Latin_Alphabet'],
    ['yombo.lib.inputtypes.latin_alphabet', 'Latin_Alphanumeric'],
    ['yombo.lib.inputtypes.yombo_items', 'Voice_Command'],
    ['yombo.lib.inputtypes.yombo_items', 'Yombo_Command'],
    ['yombo.lib.inputtypes.yombo_items', 'Yombo_Device_Type'],
    ['yombo.lib.inputtypes.yombo_items', 'Yombo_Module'],
    ['yombo.lib.inputtypes.yombo_items', 'Yombo_Device'],
]

class InputTypes(YomboLibrary):
    """
    Manages all input types available for input types.

    All modules already have a predefined reference to this library as
    `self._InputTypes`. All documentation will reference this use case.
    """
    def __contains__(self, input_type_requested):
        """
        .. note:: The input type must be enabled to be found using this method. Use :py:meth:`get <InputTypes.get>`
           to set status allowed.

        Checks to if a provided input type ID, label, or machine_label exists.

            >>> if '0kas02j1zss349k1' in self._InputTypes:

        or:

            >>> if 'living room light' in self._InputTypes:

        :raises YomboWarning: Raised when request is malformed.
        :raises KeyError: Raised when request is not found.
        :param input_type_requested: The input type id, label, or machine_label to search for.
        :type input_type_requested: string
        :return: Returns true if exists, otherwise false.
        :rtype: bool
        """
        try:
            self.get(input_type_requested)
            return True
        except:
            return False

    def __getitem__(self, input_type_requested):
        """
        .. note:: The input type must be enabled to be found using this method. Use :py:meth:`get <InputTypes.get>`
           to set status allowed.

        Attempts to find the input type requested using a couple of methods.

            >>> input_type = self._InputTypes['0kas02j1zss349k1']  #by uuid

        or:

            >>> input_type = self._InputTypes['alpnum']  #by name

        :raises YomboWarning: Raised when request is malformed.
        :raises KeyError: Raised when request is not found.
        :param input_type_requested: The input type ID, label, or machine_label to search for.
        :type input_type_requested: string
        :return: A pointer to the input type type instance.
        :rtype: instance
        """
        return self.get(input_type_requested)

    def __setitem__(self, **kwargs):
        """
        Sets are not allowed. Raises exception.

        :raises Exception: Always raised.
        """
        raise Exception("Not allowed.")

    def __delitem__(self, **kwargs):
        """
        Deletes are not allowed. Raises exception.

        :raises Exception: Always raised.
        """
        raise Exception("Not allowed.")

    def __iter__(self):
        return self.input_types.__iter__()

    def __len__(self):
        """
        Returns an int of the number of input types configured.

        :return: The number of input types configured.
        :rtype: int
        """
        return len(self.input_types)

    def __str__(self):
        """
        Returns the name of the library.
        :return: Name of the library
        :rtype: string
        """
        return "Yombo input types library"

    def keys(self):
        """
        Returns the keys (input type ID's) that are configured.

        :return: A list of input type IDs. 
        :rtype: list
        """
        return list(self.input_types.keys())

    def items(self):
        """
        Gets a list of tuples representing the input types configured.

        :return: A list of tuples.
        :rtype: list
        """
        return list(self.input_types.items())

    def iteritems(self):
        return iter(self.input_types.items())

    def iterkeys(self):
        return iter(self.input_types.keys())

    def itervalues(self):
        return iter(self.input_types.values())

    def values(self):
        return list(self.input_types.values())

    def _init_(self, **kwargs):
        """
        Setups up the basic framework. Nothing is loaded in here until the
        Load() stage.
        """
        self.load_deferred = None  # Prevents loader from moving on past _load_ until we are done.
        self.input_types = {}
        self.input_type_search_attributes = ['input_type_id', 'category_id', 'label', 'machine_label', 'description',
            'status', 'always_load', 'public']

        self.input_type_classes = {}
        self._load_local_input_type_classes()

    def _load_local_input_type_classes(self):
        for item in BASE_VALIDATORS:
            item_key = item[1].lower()
            if item_key.startswith('_'):
                item_key = item_key[1:]

            module_root = __import__(item[0], globals(), locals(), [], 0)
            # print("IT-load_validators20")
            module_tail = reduce(lambda p1, p2: getattr(p1, p2), [module_root, ] + item[0].split('.')[1:])
            # print("IT-load_validators21")
            klass = getattr(module_tail, item[1])
            # print("IT-load_validators40")
            if not isinstance(klass, collections.Callable):
                logger.warn("Unable to input type due to validator '{name}', it's not callable.", name=item[1])
                return
            # global_invoke_all('_input_types_before_import_', called_by=self, **{'input_type': input_type})
            self.input_type_classes[item_key] = klass

    def _load_(self, **kwargs):
        """
        Loads all input types from DB to various arrays for quick lookup.
        """
        self.load_deferred = Deferred()
        self._load_input_types_from_database()
        return self.load_deferred

    def _stop_(self, **kwargs):
        """
        Cleans up any pending deferreds.
        """
        if self.load_deferred is not None and self.load_deferred.called is False:
            self.load_deferred.callback(1)  # if we don't check for this, we can't stop!

    @inlineCallbacks
    def _load_input_types_from_database(self):
        """
        Loads input types from database and sends them to
        :py:meth:`import_input_types <InputTypes.import_input_types>`

        This can be triggered either on system startup or when new/updated input types have been saved to the
        database and we need to refresh existing input types.
        """
        input_types = yield self._LocalDB.get_input_types()
        logger.debug("input_types: {input_types}", input_types=input_types)
        validators_loaded = []

        for input_type in input_types:
            if input_type['machine_label'] in self.input_type_classes:
                self._import_input_type(input_type, self.input_type_classes[input_type['machine_label']])
                if input_type['machine_label'] not in validators_loaded:
                    validators_loaded.append(input_type['machine_label'])
            else:
                # print("111: %s" % input_type)
                logger.warn("Input Type '{label}' doesn't have a validator.", label=input_type['machine_label'])
                self._import_input_type(input_type, self.input_type_classes['any'])

        # now create any input_types for validators where we don't have a DB item - rare
        # print("!!!!!!!!!!!!!!!!!!!!!!!!!!  now loading missing validators....")
        # print("validators_loaded: %s" % validators_loaded)
        for validator_name, klass in self.input_type_classes.items():
            if validator_name in validators_loaded:
                continue
            logger.debug("Validator is being loaded without db entry: {validator_name}", validator_name=validator_name)
            input_type = {
                'id': validator_name,
                'label': validator_name,
                'machine_label': validator_name,
                'description': validator_name,
                'always_load': 1,
                'status': 1,
                'public': 0,
                'created_at': time(),
                'updated_at': time(),
            }
            self._import_input_type(input_type, klass)
        self.load_deferred.callback(10)

    def _import_input_type(self, input_type, klass, test_input_type=False):
        """
        Add a new input types to memory or update an existing input types.

        **Hooks called**:

        * _input_type_before_load_ : If added, sends input type dictionary as 'input_type'
        * _input_type_before_update_ : If updated, sends input type dictionary as 'input_type'
        * _input_type_loaded_ : If added, send the input type instance as 'input_type'
        * _input_type_updated_ : If updated, send the input type instance as 'input_type'

        :param input_type: A dictionary of items required to either setup a new input type or update an existing one.
        :type input: dict
        :param test_input_type: Used for unit testing.
        :type test_input_type: bool
        :returns: Pointer to new input. Only used during unittest
        """
        input_type_id = input_type["id"]
        if input_type_id not in self.input_types:
            # print("importing path: %s" % validator_data)
            self.input_types[input_type_id] = klass(self, input_type)

            # global_invoke_all('_input_type_loaded_',
            #               **{'input_type': self.input_types[input_type_id]})
        elif input_type_id not in self.input_types:
            global_invoke_all('_input_type_before_update_',
                              called_by=self,
                              id=input_type_id,
                              input_type=self.input_types[input_type_id],
                              )
            self.input_types[input_type_id].update_attributes(input_type)
            global_invoke_all('_input_type_updated_',
                              called_by=self,
                              id=input_type_id,
                              input_type=self.input_types[input_type_id],
                              )

    def get_all(self):
        """
        Returns a copy of the input types list.
        :return:
        """
        return self.input_types.copy()

    def check(self, validator_string, value, **kwargs):
        validator = self.get(validator_string)
        # print("validator: %s" % validator)
        return validator.validate(value, **kwargs)

    def get(self, input_type_requested, limiter=None, status=None):
        """
        Performs the actual search.

        .. note::

           Modules shouldn't use this function. Use the built in reference to
           find input types:

            >>> self._InputTypes['13ase45']

        or:

            >>> self._InputTypes['numeric']

        :raises YomboWarning: For invalid requests.
        :raises KeyError: When item requested cannot be found.
        :param input_type_requested: The input type ID or input type label to search for.
        :type input_type_requested: string
        :param limiter_override: Default: .89 - A value between .5 and .99. Sets how close of a match it the search should be.
        :type limiter_override: float
        :param status: Deafult: 1 - The status of the input type to check for.
        :type status: int
        :return: Pointer to requested input type.
        :rtype: dict
        """
        if limiter is None:
            limiter = .89

        if limiter > .99999999:
            limiter = .99
        elif limiter < .10:
            limiter = .10

        if input_type_requested in self.input_types:
            item = self.input_types[input_type_requested]
            if status is not None and item.status != status:
                raise KeyError("Requested input type found, but has invalid status: %s" % item.status)
            return item
        else:
            attrs = [
                {
                    'field': 'input_type_id',
                    'value': input_type_requested,
                    'limiter': limiter,
                },
                {
                    'field': 'label',
                    'value': input_type_requested,
                    'limiter': limiter,
                },
                {
                    'field': 'machine_label',
                    'value': input_type_requested,
                    'limiter': limiter,
                }
            ]
            try:
                # logger.debug("Get is about to call search...: %s" % input_type_requested)
                # found, key, item, ratio, others = self._search(attrs, operation="highest")
                found, key, item, ratio, others = do_search_instance(attrs, self.input_types,
                                                                     self.input_type_search_attributes,
                                                                     limiter=limiter,
                                                                     operation="highest")
                # logger.debug("found input type by search: {input_type_id}", input_type_id=key)
                if found:
                    return item
                else:
                    raise KeyError("Input type not found: %s" % input_type_requested)
            except YomboWarning as e:
                raise KeyError('Searched for %s, but had problems: %s' % (input_type_requested, e))

    def search(self, _limiter=None, _operation=None, **kwargs):
        """
        Search for input type based on attributes for all input types.

        :param limiter_override: Default: .89 - A value between .5 and .99. Sets how close of a match it the search should be.
        :type limiter_override: float
        :param status: Deafult: 1 - The status of the input type to check for.
        :return: 
        """
        return search_instance(kwargs,
                               self.input_types,
                               self.input_type_search_attributes,
                               _limiter,
                               _operation)

    @inlineCallbacks
    def dev_input_type_add(self, data, **kwargs):
        """
        Add a input_type at the Yombo server level, not at the local gateway level.

        :param data:
        :param kwargs:
        :return:
        """
        try:
            for key in list(data.keys()):
                if data[key] == "":
                    data[key] = None
                elif key in ['status']:
                    if data[key] is None or (isinstance(data[key], str) and data[key].lower() == "none"):
                        del data[key]
                    else:
                        data[key] = int(data[key])
        except Exception as e:
            results = {
                'status': 'failed',
                'msg': "Couldn't add input type device",
                'apimsg': e,
                'apimsghtml': e,
                'device_id': '',
            }
            return results

        try:
            input_type_results = yield self._YomboAPI.request('POST', '/v1/input_type', data)
        except YomboWarning as e:
            results = {
                'status': 'failed',
                'msg': "Couldn't add input type: %s" % e.message,
                'apimsg': "Couldn't add input type: %s" % e.message,
                'apimsghtml': "Couldn't add input type: %s" % e.html_message,
            }
            return results
        # print("dt_results: %s" % input_type_results)

        results = {
            'status': 'success',
            'msg': "Input type added.",
            'input_type_id': input_type_results['data']['id'],
        }
        return results

    @inlineCallbacks
    def dev_input_type_edit(self, input_type_id, data, **kwargs):
        """
        Edit a input_type at the Yombo server level, not at the local gateway level.

        :param data:
        :param kwargs:
        :return:
        """
        try:
            for key in list(data.keys()):
                if data[key] == "":
                    data[key] = None
                elif key in ['status']:
                    if data[key] is None or (isinstance(data[key], str) and data[key].lower() == "none"):
                        del data[key]
                    else:
                        data[key] = int(data[key])
        except Exception as e:
            results = {
                'status': 'failed',
                'msg': "Couldn't edit input type device",
                'apimsg': e,
                'apimsghtml': e,
                'device_id': '',
            }
            return results

        try:
            input_type_results = yield self._YomboAPI.request('PATCH', '/v1/input_type/%s' % (input_type_id), data)
        except YomboWarning as e:
            results = {
                'status': 'failed',
                'msg': "Couldn't edit input type: %s" % e.message,
                'apimsg': "Couldn't edit input type: %s" % e.message,
                'apimsghtml': "Couldn't edit input type: %s" % e.html_message,
            }
            return results
        # print("module edit results: %s" % module_results)

        results = {
            'status': 'success',
            'msg': "Input type edited.",
            'input_type_id': input_type_results['data']['id'],
        }
        return results

    @inlineCallbacks
    def dev_input_type_delete(self, input_type_id, **kwargs):
        """
        Delete a input_type at the Yombo server level, not at the local gateway level.

        :param input_type_id: The input_type ID to delete.
        :param kwargs:
        :return:
        """
        try:
            input_type_results = yield self._YomboAPI.request('DELETE', '/v1/input_type/%s' % input_type_id)
        except YomboWarning as e:
            results = {
                'status': 'failed',
                'msg': "Couldn't delete input type: %s" % e.message,
                'apimsg': "Couldn't delete input type: %s" % e.message,
                'apimsghtml': "Couldn't delete input type: %s" % e.html_message,
            }
            return results

        results = {
            'status': 'success',
            'msg': "Input type deleted.",
            'input_type_id': input_type_id,
        }
        return results

    @inlineCallbacks
    def dev_input_type_enable(self, input_type_id, **kwargs):
        """
        Enable a input_type at the Yombo server level, not at the local gateway level.

        :param input_type_id: The input_type ID to enable.
        :param kwargs:
        :return:
        """
        #        print "enabling input_type: %s" % input_type_id
        api_data = {
            'status': 1,
        }

        try:
            input_type_results = yield self._YomboAPI.request('PATCH', '/v1/input_type/%s' % input_type_id, api_data)
        except YomboWarning as e:
            results = {
                'status': 'failed',
                'msg': "Couldn't enable input type: %s" % e.message,
                'apimsg': "Couldn't enable input type: %s" % e.message,
                'apimsghtml': "Couldn't enable input type: %s" % e.html_message,
            }
            return results

        results = {
            'status': 'success',
            'msg': "Input type enabled.",
            'input_type_id': input_type_id,
        }
        return results

    @inlineCallbacks
    def dev_input_type_disable(self, input_type_id, **kwargs):
        """
        Enable a input_type at the Yombo server level, not at the local gateway level.

        :param input_type_id: The input_type ID to disable.
        :param kwargs:
        :return:
        """
#        print "disabling input_type: %s" % input_type_id
        api_data = {
            'status': 0,
        }

        try:
            input_type_results = yield self._YomboAPI.request('PATCH', '/v1/input_type/%s' % input_type_id, api_data)
        except YomboWarning as e:
            results = {
                'status': 'failed',
                'msg': "Couldn't disable input type: %s" % e.message,
                'apimsg': "Couldn't disable input type: %s" % e.message,
                'apimsghtml': "Couldn't disable input type: %s" % e.html_message,
            }
            return results
        # print("disable input_type results: %s" % input_type_results)

        results = {
            'status': 'success',
            'msg': "Input type disabled.",
            'input_type_id': input_type_id,
        }
        return results


