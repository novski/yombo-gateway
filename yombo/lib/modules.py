# cython: embedsignature=True
#This file was created by Yombo for use with Yombo Python Gateway automation
#software.  Details can be found at https://yombo.net
"""
Manages all modules within the system. Provides a single reference to perform module lookup functions, etc.

Also calls module hooks as requested by other libraries and modules.

.. moduleauthor:: Mitch Schwenk <mitch-gw@yombo.net>
:copyright: Copyright 2012-2016 by Yombo.
:license: LICENSE for details.
"""
# Import python libraries
#import sys
#import traceback
from time import time
import ConfigParser

# Import twisted libraries
#from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, maybeDeferred, returnValue

# Import Yombo libraries
from yombo.core.db import get_dbtools
from yombo.core.exceptions import YomboFuzzySearchError, YomboNoSuchLoadedComponentError, YomboWarning, YomboCritical
from yombo.core.fuzzysearch import FuzzySearch
from yombo.core.library import YomboLibrary
from yombo.core.log import getLogger
import yombo.utils

logger = getLogger('library.modules')

class Modules(YomboLibrary):
    """
    A single place for modudule management and reference.
    """

    _rawModulesList = {}

    _modulesByUUID = {}
    _modulesByName = FuzzySearch({}, .92)

    _moduleDevicesByUUID = {}
    _moduleDevicesByName = FuzzySearch({}, .92)

    _moduleDeviceRouting = {}
    _moduleDeviceRoutingByName = FuzzySearch({}, .95)

    _moduleDeviceTypesByUUID = {}
    _moduleDeviceTypesByName = FuzzySearch({}, .92)

    _deviceTypeRoutingByType = {}
    _modules = {}  # Stores a list of modules. Populated by the loader module at startup.

    _localModuleVars = {}  # Used to store modules variables from file import

    def _init_(self, loader):
        """
        Init doesn't do much. Just setup a few variables. Things really happen in start.
        """
        self.loader = loader
        self._DBTools = get_dbtools()

    def _load_(self):
        """
        Loads all the module information here.
        """
        pass

    def _reload_(self):
        for module in self._moduleDeviceTypesByUUID:
            for subitem in self._moduleDeviceTypesByUUID[module]:
                del self._moduleDeviceTypesByUUID[module][subitem]

        for module in self._moduleDeviceTypesByName:
            for subitem in self._moduleDeviceTypesByName[module]:
                del self._moduleDeviceTypesByName[module][subitem]

        for module in self._moduleDevicesByUUID:
            self._moduleDevicesByUUID[module].clear()

        for module in self._moduleDevicesByName:
            self._moduleDevicesByName[module].clear()

        self._moduleDeviceRouting.clear()

    def _start_(self):
        """
        Starts the library and calls self.LoadData()
        """
#        self._ModulesLibrary = self.loader.loadedComponents['yombo.gateway.lib.modules']
        self._DevicesLibrary = self.loader.loadedComponents['yombo.gateway.lib.devices']
        self.load_module_data()

    def _stop_(self):
        """
        Stop library - stop the looping call.
        """
        pass

    def _unload_(self):
        pass

    def __len__(self):
        return len(self._modulesByUUID)

    def __getitem__(self, moduleRequested):
        """
        Attempts to find the modules requested using a couple of methods.

        See get_module()
        """
        return self.get_module(moduleRequested)

#    def __iter__(self):
#        return self._modulesByUUID.__iter__()

    def __contains__(self, moduleRequested):
        try:
            self.get_module(moduleRequested)
            return True
        except:
            return False

    def load_modules(self):
        logger.debug("starting modules::load_modules !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        self.build_raw_module_list()  # Create a list of modules
        self.load_module_data()  # Load various details about modules.
        self.import_modules()  # Just call "import moduleName"

        logger.debug("starting modules::init....")
        # Init
        self.loader.library_invoke_all("_module_init_")
        self.module_init_invoke()  # Call "_init_" of modules

        # Pre-Load
        logger.debug("starting modules::pre-load....")
        self.loader.library_invoke_all("_module_preload_")
        self.module_invoke_all("_preload_")

        # Load
        self.loader.library_invoke_all("_module_load_")
        self.module_invoke_all("_load_")

        # Pre-Start
        self.loader.library_invoke_all("_module_prestart_")
        self.module_invoke_all("_prestart_")

        # Start
        self.loader.library_invoke_all("_module_start_")
        self.module_invoke_all("_start_")
        self.loader.library_invoke_all("_module_started_")

    def stop_modules(self, junk, callWhenDone):
        """
        Called when shutting down, durring reconfiguration, or downloading updated
        modules.
        """
        self.loader.library_invoke_all("_module_stop_")
        self.module_invoke_all("_stop_")
        self.loader.library_invoke_all("_module_stopped_")

        callWhenDone()

    def unload_modules(self, junk, callWhenDone):
        keys = self._modulesByUUID.keys()
        self.loader.library_invoke_all("_module_unload_")
        for moduleUUID in keys:
            module = self._modulesByUUID[moduleUUID]
            try:
                self.module_invoke(module._Name, "_unload_")
            except YomboWarning:
                pass
            finally:
                self.loader.library_invoke_all("_module_unloaded_")
                delete_component = module._FullName
                self.del_module(moduleUUID, module._Name.lower())
                del self.loader.loadedComponents[delete_component.lower()]

        callWhenDone()

    def build_raw_module_list(self):
        try:
            fp = open("localmodules.ini")
            ini = ConfigParser.SafeConfigParser()
            ini.optionxform=str
            ini.readfp(fp)
            for section in ini.sections():
                options = ini.options(section)
                mLabel = section
                mType = ''
                if 'label' in options:
                    mLabel = ini.get(section, 'label')
                    options.remove('label')
                else:
                    mLabel = section

                if 'type' in options:
                    mType = ini.get(section, 'type')
                    options.remove('type')
                else:
                    mType = 'other'

                newUUID = yombo.utils.random_string()
                self._rawModulesList[newUUID] = {
                  'localsection': section,
                  'machinelabel': mLabel,
                  'enabled': "1",
                  'moduletype': mType,
                  'moduleuuid': newUUID,
                  'installsource': 'local',
                }

                self._localModuleVars[section] = {}
                for item in options:
                    logger.debug("Adding module from localmodule.ini: {item}", item=item)
                    values = ini.get(section, item)
                    values = values.split(",")
                    vardata = {
                        'updated': int(time()),
                        'machinelabel': item.lower(),
                        'weight': 0,
                        'created': int(time()),
                        'value': values,
                        'label': item,
                        'dataweight': 0,
                        'moduleuuid': newUUID,
                        'variableuuid': 'xxx',
                    }

                    self._localModuleVars[section][item] = vardata.copy()
            logger.debug("localmodule vars: {lvars}", lvars=self._localModuleVars)
            fp.close()
        except IOError as (errno, strerror):
            logger.debug("localmodule.ini error: I/O error({errornumber}): {error}", errornumber=errno, error=strerror)

        modulesDB = self._DBTools.getModules()
        for module in modulesDB:
            self._rawModulesList[module["moduleuuid"]] = module

        logger.debug("Complete list of modules, before import: {rawModules}", rawModules=self._rawModulesList)

    def import_modules(self):
        for moduleuuid, module in self._rawModulesList.iteritems():
            pathName = "yombo.modules.%s" % module['machinelabel']
            self.loader.import_component(pathName, module['machinelabel'], 'module', module['moduleuuid'])

    @inlineCallbacks
    def module_init_invoke(self):
        """
        Calls the _init_ functions of modules. Can't use basic hook for this due to complex items.
        """
        logger.debug("Calling init functions of modules. {modules}", modules=self._modulesByUUID)
        for moduleUUID, module in self._modulesByUUID.iteritems():
            self.modules_invoke_log('debug', moduleUUID, 'module', 'init', 'About to call _init_.')
            if yombo.utils.get_method_definition_level(module._init_) != 'yombo.core.module.YomboModule':
#                logger.warn("self.get_module_devices(module['{moduleuuid}'])", moduleuuid=module.dump())
                module._ModuleType = self._rawModulesList[moduleUUID]['moduletype']
                module._ModuleUUID = moduleUUID

                module._Atoms = self.loader.loadedLibraries['atoms']
                module._States = self.loader.loadedLibraries['states']
                module._Modules = self._moduleDevicesByName
                module._Libraries = self.loader.loadedLibraries

                module._Devices = self.get_module_devices(moduleUUID)
                module._DevicesByType = getattr(self._DevicesLibrary, "getDevicesByDeviceType")
                module._DeviceTypes = self.get_module_device_types(moduleUUID)

                # Get variables, and merge with any local variable settings
                module._ModuleVariables = self._DBTools.getModuleConfigs(moduleUUID)
                if module._Name in self._localModuleVars:
                    module._ModuleVariables = yombo.utils.dict_merge(module._ModuleVariables, self._localModuleVars[module._Name])

#                module._init_()
#                continue
                try:
                    d = yield maybeDeferred(module._init_)
                except YomboCritical, e:
                    logger.error("---==(Critical Server Error in _init_ function for module: {name})==----", name=module._FullName)
                    logger.error("--------------------------------------------------------")
                    logger.error("Error message: {e}", e=e)
                    logger.error("--------------------------------------------------------")
                    e.exit()
                # except:
                #     exc_type, exc_value, exc_traceback = sys.exc_info()
                #     logger.error("------==(ERROR During _init_ of module: {module})==-------", module=module._FullName)
                #     logger.error("1:: {e}", e=sys.exc_info())
                #     logger.error("---------------==(Traceback)==--------------------------")
                #     logger.error("{e}", e=traceback.print_exc(file=sys.stdout))
                #     logger.error("--------------------------------------------------------")
                #     logger.error("{e}", e=traceback.print_exc())
                #     logger.error("--------------------------------------------------------")
                #     logger.error("{e}", e=repr(traceback.print_exception(exc_type, exc_value, exc_traceback,
                #               limit=5, file=sys.stdout)))
                #     logger.error("--------------------------------------------------------")

    def module_invoke(self, requestedModule, hook, **kwargs):
        """
        Invokes a hook for a a given module. Passes kwargs in, returns the results to caller.
        """
        module = self.get_module(requestedModule)
        if module._Name == 'yombo.core.module.YomboModule':
            raise YomboWarning("Cannot call YomboModule hooks")
        if not (hook.startswith("_") and hook.endswith("_")):
            hook = module._Name + "_" + hook
        self.modules_invoke_log('debug', requestedModule, 'module', hook, 'About to call.')
#        kwargs['_modulesLibrary'] = self
        if hasattr(module, hook):
            method = getattr(module, hook)
            if callable(method):
#                return method(**kwargs)
                try:
#                    results = yield maybeDeferred(method, **kwargs)
                    return method(**kwargs)
                except YomboCritical, e:
                    logger.error("---==(Critical Server Error in {hook} function for module: {name})==----", hook=hook, name=module._FullName)
                    logger.error("--------------------------------------------------------")
                    logger.error("Error message: {e}", e=e)
                    logger.error("--------------------------------------------------------")
                    e.exit()
#                except:
#                    exc_type, exc_value, exc_traceback = sys.exc_info()
#                    logger.error("------==(ERROR During {hooke} of module: {name})==-------", hook=hook, name=module._FullName)
#                    logger.error("1:: {e}", e=sys.exc_info())
#                    logger.error("---------------==(Traceback)==--------------------------")
#                    logger.error("{e}", e=traceback.print_exc(file=sys.stdout))
#                    logger.error("--------------------------------------------------------")
#                    logger.error("{e}", e=traceback.print_exc())
#                    logger.error("--------------------------------------------------------")
#                    logger.error("{e}", e=repr(traceback.print_exception(exc_type, exc_value, exc_traceback,
#                              limit=5, file=sys.stdout)))
#                    logger.error("--------------------------------------------------------")
            else:
                logger.error("----==(Module {module} doesn't have a callable function: {function})==-----", module=module._FullName, function=hook)

    def module_invoke_all(self, hook, fullName=False, **kwargs):
        """
        Calls module_invoke for all loaded modules.
        """
        logger.debug("in module_invoke_all: hook: {hook}", hook=hook)
        results = {}
        for moduleUUID, module in self._modulesByUUID.iteritems():
            label = module._FullName.lower() if fullName else module._Name.lower()
            try:
                 result = self.module_invoke(module._Name, hook)
                 if result is not None:
                     results[label] = result
            except YomboWarning:
                pass

        return results

    def load_module_data(self):
        """
        Load up loads of data about modules, and module devices. Makes it easy for modules to get data about what
        devices and device types they manage.
        """
        #lets clear any data, but we have to do this carefully incase of new data...
        for mdt in self._DBTools.getModuleRouting():
            # Create list of DeviceType by UUID, so a module can find all it's deviceTypes
            if mdt['moduleuuid'] not in self._moduleDeviceTypesByUUID:
                self._moduleDeviceTypesByUUID[mdt['moduleuuid']] = {}
            if mdt['devicetypeuuid'] not in self._moduleDeviceTypesByUUID[mdt['moduleuuid']]:
                self._moduleDeviceTypesByUUID[mdt['moduleuuid']][mdt['devicetypeuuid']] = []
            self._moduleDeviceTypesByUUID[mdt['moduleuuid']][mdt['devicetypeuuid']].append(mdt)
            # Pointers to the above, used when searching.
            if mdt['modulelabel'] not in self._moduleDeviceTypesByName:
                self._moduleDeviceTypesByName[mdt['modulelabel']] = FuzzySearch({}, .92)
            if mdt['devicetypeuuid'] not in self._moduleDeviceTypesByName[mdt['modulelabel']]:
                self._moduleDeviceTypesByName[mdt['modulelabel'].lower()][mdt['devicetypeuuid']] = []
            self._moduleDeviceTypesByName[mdt['modulelabel'].lower()][mdt['devicetypeuuid']].append(mdt['devicetypeuuid'])

            # How to route device types - It's here to detere what module to send to from existing modules
            if mdt['devicetypeuuid'] not in self._moduleDeviceRouting:
                self._moduleDeviceRouting[mdt['devicetypeuuid']] = {}
            self._moduleDeviceRouting[mdt['devicetypeuuid']][mdt['moduletype']] = {
                'moduleUUID' : mdt['moduleuuid'],
                'moduleLabel' : mdt['modulelabel'],
                }
            # Pointers to the above, used when searching.
            if mdt['devicetypelabel'] not in self._moduleDeviceRoutingByName:
                self._moduleDeviceRoutingByName[mdt['devicetypelabel'].lower()] = FuzzySearch({}, .92)
            self._moduleDeviceRoutingByName[mdt['devicetypelabel'].lower()][mdt['moduletype']] = {
                'moduleUUID' : mdt['moduleuuid'],
                'moduleLabel' : mdt['modulelabel'],
                }

            # Compile a list of devices for a particular module
            devices = self._DevicesLibrary.getDevicesByDeviceType(mdt['devicetypeuuid'])
            logger.debug("devices = {devices}", devices=devices)
            for deviceuuid in devices:
                logger.debug("Adding deviceUUID({deviceUUID} to self._moduleDevicesByUUID.", deviceUUID=devices[deviceuuid].deviceUUID)
                if mdt['moduleuuid'] not in self._moduleDevicesByUUID:
                    self._moduleDevicesByUUID[mdt['moduleuuid']] = {}
#                    if device['deviceuuid'] not in self._moduleDevicesByUUID[mdt['moduleuuid']]:
#                        self._moduleDevicesByUUID[mdt['moduleuuid']][device['label']] = {}
                logger.debug("Adding deviceUUID({deviceUUID} to self._moduleDevicesByUUID.", deviceUUID=devices[deviceuuid].deviceUUID)
                self._moduleDevicesByUUID[mdt['moduleuuid']][devices[deviceuuid].deviceUUID] = devices[deviceuuid]

                if mdt['moduleuuid'] not in self._moduleDevicesByName:
                    self._moduleDevicesByName[mdt['moduleuuid']] = FuzzySearch({}, .92)
#                    if device['label'] not in self._moduleDevicesByName[mdt['moduleuuid']]:
#                        self._moduleDevicesByName[mdt['moduleuuid']][device['label']] = {}
                self._moduleDevicesByName[mdt['moduleuuid']][devices[deviceuuid].label] = devices[deviceuuid].deviceUUID

            # For routing messages to modules
            if mdt['devicetypeuuid'] not in self._deviceTypeRoutingByType:
                self._deviceTypeRoutingByType[mdt['devicetypeuuid']] = {}
            self._deviceTypeRoutingByType[mdt['devicetypeuuid']][mdt['moduletype']] = mdt['modulelabel']
#            self._deviceTypeRouting[mdt['devicetypeuuid']].append([mdt['moduletype']] = mdt['modulelabel']

        logger.debug("self._moduleDeviceTypesByUUID = {moduleDeviceTypesByUUID}", moduleDeviceTypesByUUID=self._moduleDeviceTypesByUUID)
        logger.debug("self._moduleDeviceTypesByName = {moduleDeviceTypesByName}", moduleDeviceTypesByName=self._moduleDeviceTypesByName)
        logger.debug("self._moduleDeviceRouting = {moduleDeviceRouting}", moduleDeviceRouting=self._moduleDeviceRouting)
        logger.debug("self._moduleDeviceRoutingByName = {moduleDeviceRoutingByName}", moduleDeviceRoutingByName=self._moduleDeviceRoutingByName)

#        logger.info("self._moduleDeviceTypesByUUID: %s" % self._moduleDeviceTypesByUUID)

    def add_module(self, moduleUUID, moduleLabel, modulePointer):
        logger.debug("adding module: {moduleUUID}:{moduleLabel}", moduleUUID=moduleUUID, moduleLabel=moduleLabel)
        self._modulesByUUID[moduleUUID] = modulePointer
        self._modulesByName[moduleLabel] = moduleUUID

    def del_module(self, module_uuid, module_name):
        logger.debug("deleting moduleUUID: {module_uuid} from this list: {list}", module_uuid=module_uuid, list=self._modulesByUUID)
        del self._modulesByName[module_name]
        del self._modulesByUUID[module_uuid]

    def get_module(self, requestedItem):
        """
        Attempts to find the module requested using a couple of methods. Use the already defined pointer within a
        module to find another other:

            >>> someModule = self._Modules['137ab129da9318']  #by uuid
        or:
            >>> someModule = self._Modules['Homevision']  #by name

        See: :func:`yombo.core.helpers.getModule` for usage example.

        :raises KeyError: Raised when module cannot be found.
        :param requestedItem: The module UUID or module name to search for.
        :type requestedItem: string
        :return: Pointer to module.
        :rtype: module
        """
        if requestedItem in self._modulesByUUID:
            logger.debug("Looking for {requestedItem} by UUID!", requestedItem=requestedItem)
            return self._modulesByUUID[requestedItem]
        else:
            try:
                requestedUUID = self._modulesByName[requestedItem.lower()]
                logger.debug("Looking for {requestedItem}, found: {modules}", requestedItem=requestedItem, modules=requestedUUID)
                return self._modulesByUUID[requestedUUID]
            except YomboFuzzySearchError, e:
                logger.info("get_module:: not found!!! requestedItem: {requestedItem}", requestedItem=requestedItem)
                raise KeyError('Module not found.')

    def get_module_devices(self, requestedItem):
        """
        Returns all devices for a given module uuid or module name, This is used by the module library to setup a
        list of devices on startup.

            >>> devices = self._ModulesLibrary.get_module_devices('137ab129da9318')  #by uuid
        or:
            >>> devices = self._ModulesLibrary.get_module_devices('Homevision')  #by name

        :raises KeyError: Raised when module cannot be found.
        :param requestedItem: The module UUID or module name to search for.
        :type requestedItem: string
        :return: Pointer to module.
        :rtype: module
        """
#        logger.info("get_module_devices::requestedItem: {requestedItem}", requestedItem=requestedItem)
#        logger.info("get_module_devices::_moduleDevicesByUUID: {moduleDevicesByUUID}", moduleDevicesByUUID=self._moduleDevicesByUUID)
        if requestedItem in self._moduleDevicesByUUID:
            return self._moduleDevicesByUUID[requestedItem]
        else:
            try:
                requestedUUID = self._moduleDevicesByName[requestedItem.lower()]
                return self._moduleDevicesByUUID[requestedUUID]
            except YomboFuzzySearchError, e:
                return {} # no devices setup for a requested module.

    def get_module_device_types(self, requestedItem):
        """
        Returns all device types for a given module uuid or module name, This is used by the module library to setup a
        list of device types on startup.

            >>> deviceTypes = self._ModulesLibrary.get_module_device_types('137ab129da9318')  #by uuid
        or:
            >>> deviceTypes = self._ModulesLibrary.get_module_device_types('Homevision')  #by name

        :raises KeyError: Raised when module cannot be found.
        :param requestedItem: The module UUID or module name to search for.
        :type requestedItem: string
        :return: Pointer to module.
        :rtype: module
        """
        logger.debug("get_module_device_types::requestedItem: {requestedItem}", requestedItem=requestedItem)
        logger.debug("get_module_device_types::_moduleDeviceTypesByUUID: {moduleDeviceTypesByUUID}", moduleDeviceTypesByUUID=self._moduleDeviceTypesByUUID)
        if requestedItem in self._moduleDeviceTypesByUUID:
            return self._moduleDeviceTypesByUUID[requestedItem]
        else:
            try:
                logger.debug("self._moduleDeviceTypesByName: {moduleDeviceTypesByName}", moduleDeviceTypesByName=self._moduleDeviceTypesByName)
                requestedUUID = self._moduleDeviceTypesByName[requestedItem.lower()]
                return self._moduleDeviceTypesByUUID[requestedUUID]
            except YomboFuzzySearchError, e:
                logger.debug("No module found for a given device type {deviceType}", deviceType=requestedItem)
                return {}

    def get_device_routing(self, requestedItem, moduleType, returnType = 'moduleUUID'):
        """
        Device routing is used by the gateway to route a device command to the correct module. For example, a
        Z-Wave applicance module should be routed to the Z-Wave command module. From there, it needs to be routed
        to the Z-Wave interface module (the interface module is what bridges the command module to the outside world
        such as though a USB/Serial/Network interface).

        This function allows you to get the ``moduleUUID``, ``moduleLabel`` or a pointer to the ``module`` itself.

            >>> moduleUUID = self._ModulesLibrary.get_device_routing('137ab129da9318', 'Interface', 'module')  #by uuid, get the actual module pointer
        or:
            >>> deviceTypes = self._ModulesLibrary.get_device_routing('X10 Appliance', 'Command', 'moduleUUID')  #by name, get the moduleUUID
        or:
            >>> moduleUUID = self._ModulesLibrary.get_device_routing('137ab129da9318', 'Interface', 'moduleLabel')  #by uuid. get the moduleLabel

        :raises KeyError: Raised when module cannot be found.
        :param requestedItem: The module UUID or module name to search for.
        :type requestedItem: string
        :param moduleType: The module type to return. One of: Command, Interface, Logic, Other
        :type moduleType: string
        :param returnType: What type of string to return. One of: moduleUUID, moduleLabel, module
        :type returnType: string
        :return: Pointer to module.
        :rtype: module or string
        """
#        logger.debug("getModuleDeviceTypes::requestedItem: {requestedItem}", requestedItem=requestedItem)
#        logger.debug("getModuleDeviceTypes::_moduleDeviceTypesByUUID: {moduleDeviceTypesByUUID}", moduleDeviceTypesByUUID=self._moduleDeviceTypesByUUID)
        temp = None
        if requestedItem in self._moduleDeviceRouting:
            temp = self._moduleDeviceRouting[requestedItem]
        else:
            try:
                temp = self._moduleDeviceRoutingByName[requestedItem.lower()]
            except YomboFuzzySearchError, e:
                logger.debug("No route for {requestedItem}", requestedItem=requestedItem)
                return None

        if moduleType == "Command":
            if 'Command' in temp:
                temp = temp['Command']
            elif 'Interface' in temp:
                temp = temp['Interface']
            elif 'Logic' in temp:
                temp = temp['Logic']
            elif 'Other' in temp:
                temp = temp['Other']
        elif moduleType == "Interface":
            if 'Interface' in temp:
                temp = temp['Interface']
            elif 'Logic' in temp:
                temp = temp['Logic']
            elif 'Other' in temp:
                temp = temp['Other']
        elif moduleType == "Logic":
            if 'Logic' in temp:
                temp = temp['Logic']
            elif 'Other' in temp:
                temp = temp['Other']
        elif moduleType == "Other":
            if 'Other' in temp:
                temp = temp['Other']

        logger.debug("returnValue = {returnType}", returnType=returnType)

        if returnType in ("moduleUUID", "moduleLabel"):
            if temp is not None:
                return temp[returnType]
        elif returnType is 'module':
            if temp is not None:
                return self.get_module(temp['moduleUUID'])
        raise YomboNoSuchLoadedComponentError("No such loaded component:" + str(requestedItem) + " (" + str(moduleType + ")"))

    def modules_invoke_log(self, level, label, type, method, msg=""):
        """
        A common log format for loading/unloading libraries and modules.

        :param level: Log level - debug, info, warn...
        :param label: Module label "x10", "messages"
        :param type: Type of item being loaded: library, module
        :param method: Method being called.
        :param msg: Optional message to include.
        :return:
        """
        logit = func = getattr(logger, level)
        logit("({log_source}) {label}({type})::{method} - {msg}", label=label, type=type, method=method, msg=msg)