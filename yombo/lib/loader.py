# This file was created by Yombo for use with Yombo Python Gateway automation
# software.  Details can be found at https://yombo.net
"""
Responsible for importing, starting, and stopping all libraries and modules.

Starts libraries and modules (components) in the following phases.  These
phases are first completed for libraries.  After "start" phase has completed
then modules startup in the same method.

#. Import all components
#. Call "init" for all components
  * Get the component ready, but not do any actual work yet.
  * Components can now see a full list of components there were imported.
#. Call "load" for all components
#. Call "start" for all components

Stops components in the following phases. Modules first, then libraries.

#. Call "stop" for all components
#. Call "unload" for all components

.. warning::

  Module developers and users should not access any of these functions
  or variables.  This is listed here for completeness. Use a :ref:`Helpers`
  function to get what is needed.

.. moduleauthor:: Mitch Schwenk <mitch-gw@yombo.net>

:copyright: Copyright 2012-2016 by Yombo.
:license: LICENSE for details.
"""
# Import python libraries
import sys
import traceback
from re import search as ReSearch
from collections import OrderedDict
# from signal import signal, SIGINT

# Import twisted libraries
from twisted.internet.defer import inlineCallbacks, maybeDeferred, returnValue, Deferred
from twisted.internet import reactor
from twisted.web import client
client._HTTP11ClientFactory.noisy = False

# Import Yombo libraries
from yombo.core.exceptions import YomboCritical, YomboWarning, YomboNoSuchLoadedComponentError, YomboHookStopProcessing
from yombo.utils.fuzzysearch import FuzzySearch
from yombo.core.library import YomboLibrary
from yombo.core.log import get_logger
import yombo.utils

logger = get_logger('library.loader')

HARD_LOAD = OrderedDict()
HARD_LOAD["Notifications"] = {'operation_mode':'all'}
HARD_LOAD["LocalDB"] = {'operation_mode':'all'}
HARD_LOAD["SQLDict"] = {'operation_mode':'all'}
HARD_LOAD["Atoms"] = {'operation_mode':'all'}
HARD_LOAD["States"] = {'operation_mode':'all'}
HARD_LOAD["Configuration"] = {'operation_mode':'all'}
HARD_LOAD["Statistics"] = {'operation_mode':'all'}
HARD_LOAD["Startup"] = {'operation_mode':'all'}
HARD_LOAD["AMQP"] = {'operation_mode':'run'}
HARD_LOAD["YomboAPI"] = {'operation_mode':'all'}
HARD_LOAD["GPG"] = {'operation_mode':'all'}
HARD_LOAD["Automation"] = {'operation_mode':'all'}
HARD_LOAD["CronTab"] = {'operation_mode':'all'}
#HARD_LOAD["ConfigurationUpdate"] = {'operation_mode':'run'}
HARD_LOAD["DownloadModules"] = {'operation_mode':'run'}
HARD_LOAD["Times"] = {'operation_mode':'all'}
HARD_LOAD["Commands"] = {'operation_mode':'all'}
HARD_LOAD["DeviceTypes"] = {'operation_mode':'all'}
HARD_LOAD["InputTypes"] = {'operation_mode':'all'}
HARD_LOAD["VoiceCmds"] = {'operation_mode':'all'}
HARD_LOAD["Devices"] = {'operation_mode':'all'}
HARD_LOAD["Modules"] = {'operation_mode':'all'}
# HARD_LOAD["AutomationHelpers"] = {'operation_mode':'all'}
HARD_LOAD["MQTT"] = {'operation_mode':'run'}
HARD_LOAD["Localize"] = {'operation_mode':'all'}
HARD_LOAD["AMQPYombo"] = {'operation_mode':'run'}
HARD_LOAD["WebInterface"] = {'operation_mode':'all'}

HARD_UNLOAD = OrderedDict()
HARD_UNLOAD["Localize"] = {'operation_mode':'all'}
HARD_UNLOAD["Startup"] = {'operation_mode':'all'}
HARD_UNLOAD["YomboAPI"] = {'operation_mode':'all'}
HARD_UNLOAD["GPG"] = {'operation_mode':'all'}
HARD_UNLOAD["Automation"] = {'operation_mode':'all'}
HARD_UNLOAD["CronTab"] = {'operation_mode':'all'}
HARD_UNLOAD["Times"] = {'operation_mode':'all'}
HARD_UNLOAD["Commands"] = {'operation_mode':'all'}
HARD_UNLOAD["DeviceTypes"] = {'operation_mode':'all'}
HARD_UNLOAD["InputTypes"] = {'operation_mode':'all'}
HARD_UNLOAD["VoiceCmds"] = {'operation_mode':'all'}
# HARD_UNLOAD["AutomationHelpers"] = {'operation_mode':'all'}
HARD_UNLOAD["Devices"] = {'operation_mode':'all'}
HARD_UNLOAD["Atoms"] = {'operation_mode':'all'}
HARD_UNLOAD["States"] = {'operation_mode':'all'}
HARD_UNLOAD["WebInterface"] = {'operation_mode':'all'}
HARD_UNLOAD["Devices"] = {'operation_mode':'all'}
HARD_UNLOAD["AMQPYombo"] = {'operation_mode':'run'}
HARD_UNLOAD["Configuration"] = {'operation_mode':'all'}
HARD_UNLOAD["Statistics"] = {'operation_mode':'all'}
HARD_UNLOAD["Modules"] = {'operation_mode':'all'}
HARD_UNLOAD["MQTT"] = {'operation_mode':'run'}
HARD_UNLOAD["SQLDict"] = {'operation_mode':'all'}
HARD_UNLOAD["AMQP"] = {'operation_mode':'run'}
HARD_UNLOAD["Modules"] = {'operation_mode':'all'}
# HARD_UNLOAD["DownloadModules"] = {'operation_mode':'run'}
HARD_UNLOAD["LocalDB"] = {'operation_mode':'all'}


class Loader(YomboLibrary, object):
    """
    Responsible for loading libraries, and then delegating loading modules to
    the modules library.

    Libraries are never reloaded, however, during a reconfiguration,
    modules are unloaded, and then reloaded after configurations are done
    being downloaded.
    """
    @property
    def operation_mode(self):
        return self._operation_mode

    @operation_mode.setter
    def operation_mode(self, val):
        self.loadedLibraries['atoms']['loader.operation_mode'] = val
        self._operation_mode = val

    def __getitem__(self, component_requested):
        """
        """
        logger.debug("looking for: {component_requested}", component_requested=component_requested)
        if component_requested in self.loadedComponents:
            logger.debug("found by loadedComponents! {component_requested}", component_requested=component_requested)
            return self.loadedComponents[component_requested]
        elif component_requested in self.loadedLibraries:
            logger.debug("found by loadedLibraries! {component_requested}", component_requested=component_requested)
            return self.loadedLibraries[component_requested]
        elif component_requested in self._moduleLibrary:
            logger.debug("found by self._moduleLibrary! {component_requested}", component_requested=self._moduleLibrary)
            return self._moduleLibrary[component_requested]
        else:
            raise YomboWarning("Loader could not find requested component: {%s}"
                               % component_requested, '101', '__getitem__', 'loader')

    def __init__(self, testing=False):
        self.unittest = testing
        self._moduleLibrary = None
        YomboLibrary.__init__(self)

        self.loadedComponents = FuzzySearch({self._FullName.lower(): self}, .95)
        self.loadedLibraries = FuzzySearch({self._Name.lower(): self}, .95)
        self.libraryNames = {}
        self.__localModuleVars = {}
        self._moduleLibrary = None
        self._invoke_list_cache = {}  # Store a list of hooks that exist or not. A cache.
        self._operation_mode = None  # One of: firstrun, config, run
        self.sigint = False  # will be set to true if SIGINT is received
        self.hook_counts = OrderedDict()  # keep track of hook names, and how many times it's called.
        reactor.addSystemEventTrigger("before", "shutdown", self.shutdown)
        # signal(SIGINT, self.shutdown2)

    def shutdown(self):
        """
        This is called if SIGINT (ctrl-c) was caught. Very useful incase it was called during startup.
        :return:
        """
        print "SIGINT received - twisted"
        self.sigint = True

    # def shutdown2(self, signum, frame):
    #     """
    #     This is called if SIGINT (ctrl-c) was caught. Very useful incase it was called during startup.
    #     :return:
    #     """
    #     print 'Signal handler called with signal %s' % signum
    #     print "WHAT!  I was called - signal"
    #     self.sigint = True
    #     reactor.stop()

    @inlineCallbacks
    def start(self):  #on startup, load libraried, then modules
        """
        This is effectively the main start function.

        This function is called when the gateway is to startup. In turn,
        this function will load all the components and modules of the gateway.
        """
        logger.info("Importing libraries, this can take a few moments.")
        yield self.import_libraries() # import and init all libraries
        # returnValue(None)

        # if self.sigint:
        #     return
        logger.debug("Calling load functions of libraries.")
        for name, config in HARD_LOAD.iteritems():
#            print "sigint: %s" % self.sigint
#             if self.sigint:
#                 return
            self._log_loader('debug', name, 'library', 'load', 'About to call _load_.')
            if self.check_operation_mode(config['operation_mode']):
                HARD_LOAD[name]['_load_'] = 'Starting'
                libraryName = name.lower()
                yield self.library_invoke(libraryName, "_load_", self)
                HARD_LOAD[name]['_load_'] = True
            else:
                HARD_LOAD[name]['_load_'] = False
            self._log_loader('debug', name, 'library', 'load', 'Finished call to _load_.')

        self._moduleLibrary = self.loadedLibraries['modules']
#        logger.debug("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1Calling start function of libraries.")
        for name, config in HARD_LOAD.iteritems():
            if self.sigint:
                return
            self._log_loader('debug', name, 'library', 'start', 'About to call _start_.')
            if self.check_operation_mode(config['operation_mode']):
                libraryName =  name.lower()
                yield self.library_invoke(libraryName, "_start_", self)
                HARD_LOAD[name]['_start_'] = True
            else:
                HARD_LOAD[name]['_start_'] = False

        for name, config in HARD_LOAD.iteritems():
            if self.sigint:
                return
            self._log_loader('debug', name, 'library', 'started', 'About to call _started_.')
            if self.check_operation_mode(config['operation_mode']):
                libraryName =  name.lower()
                yield self.library_invoke(libraryName, "_started_", self)
                HARD_LOAD[name]['_started_'] = True
            else:
                HARD_LOAD[name]['_started_'] = False

        yield self._moduleLibrary.load_modules()
        self.loadedLibraries['notifications'].add({'title': 'System started',
            'message': 'System successfully started.', 'timeout': 300, 'source': 'Yombo Gateway System',
            'persist': False,
            'always_show': False,
        })

    @inlineCallbacks
    def unload(self):
        """
        Called when the gateway should stop. This will gracefully stop the gateway.

        First, unload all modules, then unload all components.
        """
        self.sigint = True  # it's 99.999% true - usually only shutdown due to this.
        if self._moduleLibrary is not None:
            yield self._moduleLibrary.unload_modules()
        yield self.unload_components()

    def Times_i18n_atoms(self, **kwargs):
       return [
           {'loader.operation_mode': {
               'en': 'One of: firstrun, run, config',
               },
           },
       ]

    def check_component_status(self, name, function):
        if name in HARD_LOAD:
            if function in HARD_LOAD[name]:
                return HARD_LOAD[name][function]
        return None

    def _log_loader(self, level, label, type, method, msg=""):
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
        logit("Loader: {label}({type})::{method} - {msg}", label=label, type=type, method=method, msg=msg)

    @inlineCallbacks
    def import_libraries(self):
        """
        Import then "init" all libraries. Call "loadLibraries" when done.
        """
        logger.debug("Importing server libraries.")
        for name, config in HARD_LOAD.iteritems():
            if self.sigint:
                return
            HARD_LOAD[name]['__init__'] = 'Starting'
            pathName = "yombo.lib.%s" % name
            self.import_component(pathName, name, 'library')
            HARD_LOAD[name]['__init__'] = True

        logger.debug("Calling init functions of libraries.")
        for name, config in HARD_LOAD.iteritems():
            if self.sigint:
                return
            if self.check_operation_mode(config['operation_mode']) is False:
                HARD_LOAD[name]['_init_'] = False
                continue
            HARD_LOAD[name]['_init_'] = 'Starting'
            self._log_loader('debug', name, 'library', 'init', 'About to call _init_.')

            component = name.lower()
            library = self.loadedLibraries[component]
            library._AMQP = self.loadedLibraries['amqp']
            library._Atoms = self.loadedLibraries['atoms']
            library._Commands = self.loadedLibraries['commands']
            library._Configs = self.loadedLibraries['configuration']
            library._Devices = self.loadedLibraries['devices']
            library._DeviceTypes = self.loadedLibraries['devicetypes']
            library._InputTypes = self.loadedLibraries['inputtypes']
            library._Libraries = self.loadedLibraries
            library._Loader = self
            library._Modules = self._moduleLibrary
            library._Notifications = self.loadedLibraries['notifications']
            library._Localize = self.loadedLibraries['localize']
            library._MQTT = self.loadedLibraries['mqtt']
            library._SQLDict = self.loadedLibraries['sqldict']
            library._States = self.loadedLibraries['states']
            library._Statistics = self.loadedLibraries['statistics']
            library._YomboAPI = self.loadedLibraries['yomboapi']
            if hasattr(library, '_init_') and callable(library._init_) \
                    and yombo.utils.get_method_definition_level(library._init_) != 'yombo.core.module.YomboModule':
                d = yield maybeDeferred(library._init_)
                self._log_loader('debug', name, 'library', 'init', 'Finished to call _init_.')
                # try:
                #     d = yield maybeDeferred(library._init_, self)
                # except YomboCritical, e:
                #     logger.error("---==(Critical Server Error in init function for library: {name})==----", name=name)
                #     logger.error("--------------------------------------------------------")
                #     logger.error("Error message: {e}", e=e)
                #     logger.error("--------------------------------------------------------")
                #     e.exit()
                # except:
                #     logger.error("-------==(Error in init function for library: {name})==---------", name=name)
                #     logger.error("1:: {e}", e=sys.exc_info())
                #     logger.error("---------------==(Traceback)==--------------------------")
                #     logger.error("{e}", e=traceback.print_exc(file=sys.stdout))
                #     logger.error("--------------------------------------------------------")
                HARD_LOAD[name]['_init_'] = True
            else:
                logger.error("----==(Library doesn't have init function: {name})==-----", name=name)

    def check_operation_mode(self, allowed):
        """
        Checks if something should be run based on the current operation_mode.
        :param config: Either string or list or posible operation_modes
        :return: True/False
        """
        op_mode = self.operation_mode

        if op_mode is None:
            return True

        def check_operation_mode_inside(mode, op_mode):
            if mode == 'all':
                return True
            elif mode == op_mode:
                return True
            return False

        if isinstance(allowed, basestring):  # we have a string
            return check_operation_mode_inside(allowed, op_mode)
        else: # we have something else
            for item in allowed:
                if check_operation_mode_inside(item, op_mode):
                    return True

    @inlineCallbacks
    def library_invoke(self, requested_library, hook, called_by=None, **kwargs):
        """
        Invokes a hook for a a given library. Passes kwargs in, returns the results to caller.
        """
        if requested_library not in self.loadedLibraries:
            returnValue(None)
        if called_by is not None:
            called_by = called_by._FullName
        else:
            called_by = 'Unknown'

        cache_key = requested_library + hook
        if cache_key in self._invoke_list_cache:
            if self._invoke_list_cache[cache_key] is False:
                # logger.warn("Cache hook ({cache_key})...SKIPPED", cache_key=cache_key)
                returnValue(None) # skip. We already know function doesn't exist.
        library = self.loadedLibraries[requested_library]
        if requested_library == 'Loader':
            returnValue(None)
        if not (hook.startswith("_") and hook.endswith("_")):
            hook = library._Name.lower() + "_" + hook
        if hasattr(library, hook):
            method = getattr(library, hook)
            self._log_loader('debug', requested_library, 'library', 'library_invoke', 'About to call: %s' % hook)
            if callable(method):
                if library._Name not in self.hook_counts:
                    self.hook_counts[library._Name] = {}
                if hook not in self.hook_counts:
                    self.hook_counts[library._Name][hook] = {'Total Count': {'count': 0}}
                # print "hook counts: %s" % self.hook_counts
                # print "hook counts: %s" % self.hook_counts[library._Name][hook]
                if called_by not in self.hook_counts[library._Name][hook]:
                    self.hook_counts[library._Name][hook][called_by] = {'count': 0}
                self.hook_counts[library._Name][hook][called_by]['count'] = self.hook_counts[library._Name][hook][called_by]['count'] + 1
                self.hook_counts[library._Name][hook]['Total Count']['count'] = self.hook_counts[library._Name][hook]['Total Count']['count'] + 1
                self._invoke_list_cache[cache_key] = True
                results = yield maybeDeferred(method, **kwargs)
                self._log_loader('debug', requested_library, 'library', 'library_invoke', 'Finished with call: %s' % hook)
                returnValue(results)
            else:
                logger.warn("Cache library hook ({library}:{hook})...setting false", library=library._FullName, hook=hook)
                logger.debug("----==(Library {library} doesn't have a callable function: {function})==-----", library=library._FullName, function=hook)
                raise YomboWarning("Hook is not callable: %s" % hook)
        else:
#            logger.debug("Cache hook ({library}:{hook})...setting false", library=library._FullName, hook=hook)
            self._invoke_list_cache[cache_key] = False

    def library_invoke_all(self, hook, fullName=False, called_by=None, **kwargs):
        """
        Calls library_invoke for all loaded libraries.
        """
        results = {}
        to_process = {}
        if 'components' in kwargs:
            to_process = kwargs['components']
        else:
            for library_name, library in self.loadedLibraries.iteritems():
#                print "library %s" % library
                label = library._FullName.lower() if fullName else library._Name.lower()
                to_process[library_name] = label

        for library_name, library in self.loadedLibraries.iteritems():
            # logger.debug("invoke all:{libraryName} -> {hook}", libraryName=library_name, hook=hook )
            try:
                d = self.library_invoke(library_name, hook, called_by=called_by, **kwargs)
                if isinstance(d, Deferred):
                    result = getattr(d, 'result', None)
                    if result is not None:
#                      logger.warn("1111aaa:: {libraryName} {hook} {result}", libraryName=libraryName, hook=hook, result=result)
                      results[library._FullName] = result
            except YomboWarning:
                pass
            except YomboHookStopProcessing as e:
                e.collected = results
                e.by_who =  label
                raise

        return results

    def import_component(self, pathName, componentName, componentType, componentUUID=None):
        """
        Load component of given name. Can be a core library, or a module.
        """
        pymodulename = pathName.lower()
        self._log_loader('debug', componentName, componentType, 'import', 'About to import.')
        try:
            pyclassname = ReSearch("(?<=\.)([^.]+)$", pathName).group(1)
        except AttributeError:
            self._log_loader('error', componentName, componentType, 'import', 'Not found. Path: %s' % pathName)
            logger.error("Library or Module not found: {pathName}", pathName=pathName)
            raise YomboCritical("Library or Module not found: %s", pathName)
        try:
#            print "pymodulename: %s" % pymodulename
            module_root = __import__(pymodulename, globals(), locals(), [], 0)
            pass
        except ImportError as detail:
            self._log_loader('error', componentName, componentType, 'import', 'Not found. Path: %s' % pathName)
            logger.error("--------==(Error: Library or Module not found)==--------")
            logger.error("----Name: {pathName},  Details: {detail}", pathName=pathName, detail=detail)
            logger.error("--------------------------------------------------------")
            logger.error("{error}", error=sys.exc_info())
            logger.error("---------------==(Traceback)==--------------------------")
            logger.error("{trace}", trace=traceback.print_exc(file=sys.stdout))
            logger.error("--------------------------------------------------------")
            return

        module_tail = reduce(lambda p1, p2: getattr(p1, p2), [module_root, ]+pymodulename.split('.')[1:])
        # print "module_tail: %s   pyclassname: %s" % (module_tail, pyclassname)
        klass = getattr(module_tail, pyclassname)
        # print "klass: %s  " % klass

        # Put the component into various lists for mgmt
        if not callable(klass):
            logger.warn("Unable to start class '{classname}', it's not callable.", classname=pyclassname)
            return

        try:
            # Instantiate the class
            moduleinst = klass()  # start the class, only libraries get the loader
            if componentType == 'library':
                if componentName.lower() == 'modules':
                    self._moduleLibrary = moduleinst

                self.loadedComponents["yombo.gateway.lib." + str(componentName.lower())] = moduleinst
                self.loadedLibraries[str(componentName.lower())] = moduleinst
                # this is mostly for manhole module, but maybe useful elsewhere?
                temp = componentName.split(".")
                self.libraryNames[temp[-1]] = moduleinst
            else:
                self.loadedComponents["yombo.gateway.modules." + str(componentName.lower())] = moduleinst
                self._moduleLibrary.add_imported_module(componentUUID, str(componentName.lower()), moduleinst)

        except YomboCritical, e:
            logger.debug("@!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            logger.debug("{e}", e=e)
            logger.debug("@!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            e.exit()
            raise

    @inlineCallbacks
    def unload_components(self):
        """
        Only called when server is doing shutdown. Stops controller, server control and server data..
        """
        logger.debug("Stopping libraries: {stuff}", stuff=HARD_UNLOAD)
        for name, config in HARD_UNLOAD.iteritems():
            if self.check_operation_mode(config['operation_mode']):
                HARD_UNLOAD[name]['_stop_'] = 'Running'
                libraryName = name.lower()
                logger.debug("stopping: {name}", name=name)
                yield self.library_invoke(name, "_stop_")
                HARD_UNLOAD[name]['_stop_'] = True
            else:
                HARD_UNLOAD[name]['_stop_'] = False

        for name, config in HARD_UNLOAD.iteritems():
            if self.check_operation_mode(config['operation_mode']):
                HARD_UNLOAD[name]['_unload_'] = 'Running'
                libraryName = name.lower()
                logger.debug("_unload_: {name}", name=name)
                yield self.library_invoke(name, "_unload_")
                HARD_UNLOAD[name]['_unload_'] = True
            else:
                HARD_UNLOAD[name]['_unload_'] = False


    def _handleError(self, err):
#        logger.error("Error caught: %s", err.getErrorMessage())
#        logger.error("Error type: %s  %s", err.type, err.value)
        err.raiseException()

    def get_loaded_component(self, name):
        """
        Returns loaded module object by name. Module must be loaded.
        """
        try:
            return self.loadedComponents[name.lower()]
        except KeyError:
            raise YomboNoSuchLoadedComponentError("No such loaded component: %s" % str(name))

    def get_all_loaded_components(self):
        """
        Returns loaded module object by name. Module must be loaded.
        """
        return self.loadedComponents


_loader = None

def setup_loader(testing=False):
    global _loader
    if not _loader:
        _loader = Loader(testing)
    return _loader

def get_loader():
    global _loader
    return _loader

def get_the_loaded_components():
    global _loader
    return _loader.get_all_loaded_components()

def stop_loader():
    global _loader
    if not _loader:
        return
    else:
        _loader.unload()
    return