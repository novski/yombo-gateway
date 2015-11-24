# This file was created by Yombo for use with Yombo Python gateway automation
# software.  Details can be found at https://yombo.net
"""
A database API to SQLite3.

.. warning::

   These functions, variables, and classes **should not** be accessed directly
   by modules. These are documented here for completeness. Use (or create) a
   :ref:`helpers` function to get what is needed.

   If additional information is needed to/from the database, open a feature
   request at `<https://projects.yombo.net/>` under the Gateway Project.

.. warning::

   This entire file will be re-written in a future version. An attempt
   was made to make this non-blocking, but it was not completly successfull.
   Do not rely on these function names to remain the same.

.. moduleauthor:: Mitch Schwenk <mitch-gw@yombo.net>
:copyright: Copyright 2012-2015 by Yombo.
:license: LICENSE for details.
"""
# Import python libraries
import cPickle
from itertools import izip
import sqlite3
import time

# Import Yombo libraries
from yombo.core.log import getLogger

logger = getLogger('core.db')

yombodbpool = None
yombotoolsdb = None


def get_dbtools():
    """
    Return connection to database.
    """
    global yombotoolsdb
    return yombotoolsdb


class DBConnectionPool:
    """
    Create a connection pool between the SQL requests and the actual database
    itself.
    """

    def connect(self):
        SQLITE3_PATH = "usr/sql/config.sqlite3"
        self.pool = sqlite3.connect(SQLITE3_PATH)
        self.cur = self.pool.cursor()
        self._create_tables_if_not_exist()

    def cursor(self):
        return self.pool.cursor()

    def commit(self):
        self.pool.commit()

    def _create_tables_if_not_exist(self):
        for table in ALLTABLES:
            lines = table.sql()
            for line in lines:
                #                logger.info("line: %s" % line)
                self.cur.execute(line)
        self.pool.commit()

    def loadall(self, data):
        output = [c for c in data]
        return output

    def returnOk(self, o):
        return True

    def returnFailure(self, o):
        logger.warning("returnfailure: %s", o)
        return False

    def returnResult(self, result):
        return result

    def returnResultDict(self, result, fields):
        data = []
        for row in result:
            data.append(dict(zip(fields, row)))
        return data

    def _returnResult(self, deferred, count=None):
        if count:
            return self.pool.fetchmany(count)
        else:
            return self.pool.fetchall()

    def execSql(self, sql, params={}):
        def run(sql, params):
            return self.pool.runQuery(sql, params)

        d = run(sql, params)
        d.addErrback(self.returnFailure)
        d.addCallback(self.returnResult)
        return d

    def fetch(self, sql, params={}):
        def run(sql, params):
            return self.pool.runQuery(sql, params)

        logger.trace("fetch: %s", sql)
        d = run(sql, params)
        d.addCallback(self.returnResult)
        d.addErrback(self.returnFailure)
        return d

    def fetchDict(self, sql, fields, params={}):
        def run(sql, params):
            return self.pool.runQuery(sql, params)

        d = run(sql, params)
        d.addCallback(self.returnResultDict, fields)
        d.addErrback(self.returnFailure)
        return d

    def select(self, table, fields=None, additional="", positional=[]):
        """
        Return result of select statement.

        :param table: name of db table
        :type table: string
        :param fields: list of fields to select
        :type fields: list
        :param additional: additional SQL added to the end of query such as WHERE
        :type additional: string
        :param positional: values that will be replaced instead of '?' in SQL query (and escaped)
        :type positional: list
        """
        query = "SELECT %s FROM %s %s" % (
            ", ".join("`%s`" % field for field in fields) if fields else " * ",
            table,
            additional,
        )

        #        if isinstance(positional, str):
        #            positional = (positional,)

        logger.trace("SQL: '%s", query)
        return self.fetchDict(query, fields)


def get_dbconnection():
    """
    Return connection to database, creating it if necessary.
    """
    global yombodbpool
    global yombotoolsdb
    if yombodbpool is None:
        logger.debug("Creating db connection pools.")
        yombodbpool = DBConnectionPool()
        yombodbpool.connect()
        yombotoolsdb = DBTools(yombodbpool)
    return yombodbpool


class DBTools:
    """
    Various DB tools. Usses the DB pool above to perform the actual
    work.
    """

    def __init__(self, dbpool=None):
        if dbpool is None:
            self.dbpool = get_dbconnection()
        else:
            self.dbpool = dbpool

    def get_cmd_by_uuid(self, cmdid):
        c = self.dbpool.cursor()
        c.execute('SELECT * FROM commands WHERE cmdUUID = ?', (cmdid,))
        row = c.fetchone()
        if row is None:
            return None
        field_names = [d[0].lower() for d in c.description]
        return dict(izip(field_names, row))

    def get_cmduuid_by_cmd(self, cmd):
        c = self.dbpool.cursor()
        c.execute('SELECT * FROM commands WHERE cmd = "?"', (cmd,))
        row = c.fetchone()
        if row is None:
            return None
        field_names = [d[0].lower() for d in c.description]
        return dict(izip(field_names, row))

    def get_cmduuid_by_voicecmd(self, voicecmd):
        c = self.dbpool.cursor()
        c.execute("SELECT * FROM commands WHERE voiceCmd = '%s'" % (voicecmd,))
        row = c.fetchone()
        if row is None:
            return None
        field_names = [d[0].lower() for d in c.description]
        return dict(izip(field_names, row))

    def get_module_by_name(self, modulelabel):
        c = self.dbpool.cursor()
        c.execute('SELECT * FROM modules WHERE machinelabel = ?', (modulelabel,))
        row = c.fetchone()
        if row is None:
            return None
        field_names = [d[0].lower() for d in c.description]
        return dict(izip(field_names, row))

    def getModuleDeviceTypes(self):
        c = self.dbpool.cursor()
        c.execute('SELECT * FROM moduleDeviceTypes ' +
                  'JOIN deviceTypes on moduleDeviceTypes.deviceTypeUUID = deviceTypes.deviceTypeUUID ' +
                  'GROUP BY moduleDeviceTypes.deviceTypeUUID, moduleDeviceTypes.moduleType ' +
                  'ORDER BY priority DESC')
        data = c.fetchall()
        if data is None:
            return None
        records = []
        field_names = [d[0].lower() for d in c.description]
        for row in data:
            records.append(dict(izip(field_names, row)))
        return records

    def getCommandsForDeviceType(self, deviceuuid):
        c = self.dbpool.cursor()
        c.execute('SELECT * FROM deviceTypeCommands WHERE deviceTypeUUID = ?', (deviceuuid,))
        data = c.fetchall()
        if data is None:
            return None
        records = []
        field_names = [d[0].lower() for d in c.description]
        for row in data:
            item = dict(izip(field_names, row))
            records.append(item['cmduuid'])
        return records

    def get_messageDelayed(self):
        c = self.dbpool.cursor()
        c.execute("SELECT * FROM messageDelayed")
        data = c.fetchall()
        if data is None:
            return None
        records = []
        field_names = [d[0].lower() for d in c.description]
        for row in data:
            item = dict(izip(field_names, row))
            records.append(item['message'])
        return records

    def validateDeviceTypeUUID(self, cmduuid, devicetypeuuid):
        """
        Used in the message clas to verify if a given devicetypeuud and cmduuid are valid.
        """
        c = self.dbpool.cursor()
        c.execute("select deviceTypeUUID from deviceTypeCommands where cmdUUID = '%s' and deviceTypeUUID = '%s'" %
                  (cmduuid, devicetypeuuid))
        row = c.fetchone()
        if row is None:
            return None
        field_names = [d[0].lower() for d in c.description]
        return dict(izip(field_names, row))

    def getModules(self, getAll=False):
        c = self.dbpool.cursor()
        if getAll is False:
            c.execute("SELECT * FROM modules WHERE status = 1")
        else:
            c.execute("SELECT * FROM modules WHERE")
        data = c.fetchall()
        if data is None:
            return None
        records = []
        field_names = [d[0].lower() for d in c.description]
        for row in data:
            records.append(dict(izip(field_names, row)))
        return records

    def getModuleVariables(self, modulelabel):
        from yombo.core.helpers import pgpDecrypt
        c = self.dbpool.cursor()
        module = self.get_module_by_name(modulelabel)
        if module is None:
            return {}

        c.execute('SELECT * FROM moduleVariables WHERE moduleuuid = ? order by weight ASC, dataWeight ASC',
                  (module["moduleuuid"],))
        data = c.fetchall()
        if data is None or len(data) == 0:
            return {}
        records = {}
        field_names = [d[0].lower() for d in c.description]
        for row in data:
            record = dict(izip(field_names, row))
#            varnames = cPickle.loads(str(record['varnames']))
#            varvalues = cPickle.loads(str(record['varvalues']))
#            logger.info("variable_modules = %s", record)
            records[record['machinelabel']] = record
        return records

    def getUserGWToken(self, username, gwtokenid):
        c = self.dbpool.cursor()

        c.execute('SELECT * FROM gwTokens WHERE username = ? and gwtokenid = ?', (username, gwtokenid))
        row = c.fetchone()
        if row is None:
            return None
        field_names = [d[0].lower() for d in c.description]
        return dict(izip(field_names, row))

    def getVariableDevices(self, deviceuuid):
        from yombo.core.helpers import pgpDecrypt
        c = self.dbpool.cursor()

        c.execute('SELECT * FROM variableDevices WHERE deviceUUID = ? order by weight ASC, dataWeight ASC',
                  (deviceuuid,))
        data = c.fetchall()
        if data is None or len(data) == 0:
            return None
        records = {}
        field_names = [d[0].lower() for d in c.description]
        for row in data:
            record = dict(izip(field_names, row))
            varnames = cPickle.loads(str(record['varnames']))
            varvalues = cPickle.loads(str(record['varvalues']))
            #            logger.trace("varnames = %s", varnames)
            #            logger.trace("varvalues = %s", varvalues)
            items = []
            for namekey in varnames:
                if namekey not in varvalues:
                    continue
                items.append(varvalues[namekey])
                if varnames[namekey] not in records:
                    records[varnames[namekey]] = []
                records[varnames[namekey]].append(pgpDecrypt(varvalues[namekey]))
            #        logger.info("variable_modules = %s", records)
        return records

    def get_module_data_by_key(self, modulename, key1, key2='', type='data'):
        if key1 == '':
            return False
        c = self.dbpool.cursor()
        sql = "SELECT rowid, data1 FROM moduleData WHERE key1 = '%s'" % (key1,)
        if key1 != '':
            sql = sql + " AND key2 = '%s'" % (key2,)
        #        logger.debug("get_moduledData: %s", sql)
        c.execute(sql)
        row = c.fetchone()
        if row is None:
            return None
        field_names = [d[0].lower() for d in c.description]
        record = dict(izip(field_names, row))
        if type != 'data':
            return record['rowid']
        else:
            return record['data1']

    def set_module_data_by_key(self, modulename, key1, key2='', data1=None):
        if key1 == '' or data1 is None:
            return False

        rowid = self.get_module_data_by_key(modulename, key1, key2, 'rowid')
        c = self.dbpool.cursor()
        if rowid is False:
            c.execute("""
                update moduleData set data1=? where rowid=?;""", (data1, rowid))
        else:
            c.execute("""
                replace into moduleData (key1, key2, data1)
                values  (?, ?, ?);""", (key1, key2, data1))
        # """   """

    def saveSQLDict(self, module, dictname, key1, data1):
        c = self.dbpool.cursor()

        c.execute(
            "select rowid from sqldict where key1='%s' and module='%s' and dictname='%s'" % (key1, module, dictname))
        row = c.fetchone()
        if row:
            field_names = [d[0].lower() for d in c.description]
            record = dict(izip(field_names, row))
            c.execute("update sqldict set data1=?, updated=? where rowid=?;",
                      (data1, int(time.time()), record['rowid']))
        else:
            c.execute("""
                replace into sqldict (created, updated, module, dictname, key1, data1)
                values  (?, ?, ?, ?, ?, ?);""", (int(time.time()), int(time.time()), module, dictname, key1, data1))
        # """   """

    def commit(self):
        self.dbpool.commit()


class BaseColumn:
    is_id = False

    def __init__(self, update=True, index=False, unique=False,
                 primary_key=False, name=None):
        self.update = update
        self.index = index
        self.unique = unique
        self.primary_key = primary_key
        self.name = name
        if not self.affinity:
            self.affinity = ""

    def __repr__(self):
        return "<Column '%s' affinity:;%s%s%s%s>" % (self.name, self.affinity,
                                                     " index" if self.index else "",
                                                     " unique" if self.unique else "",
                                                     " primary_key" if self.primary_key else "")

    def sql(self):
        modifiers = [self.name]
        if self.affinity:
            modifiers.append(self.affinity)
        if self.index:
            modifiers.append("INDEX")
        if self.unique:
            modifiers.append("UNIQUE")
        if self.primary_key:
            modifiers.append("PRIMARY KEY")

        return " ".join(modifiers)


class TextColumn(BaseColumn):
    affinity = "TEXT"


class NumericColumn(BaseColumn):
    affinity = "NUMERIC"


class IntegerColumn(BaseColumn):
    affinity = "INTEGER"


class BlobColumn(BaseColumn):
    affinity = "BLOB"


class RealColumn(BaseColumn):  # floating type
    affinity = "REAL"


class BooleanColumn(IntegerColumn):
    pass


class IntegerPKColumn(IntegerColumn):
    def __init__(self, *args, **kwargs):
        kwargs['primary_key'] = True
        IntegerColumn.__init__(self, *args, **kwargs)


class TextPKColumn(TextColumn):
    def __init__(self, *args, **kwargs):
        kwargs['primary_key'] = True
        TextColumn.__init__(self, *args, **kwargs)


class ForeignKeyColumn(IntegerColumn):
    pass


class TableMeta(type):
    def __new__(cls, class_name, bases, attrs):
        columns = []
        columnsByName = {}
        indexes = []
        new_attrs = {}
        for n, v in attrs.iteritems():
            if isinstance(v, BaseColumn):
                if not v.name:
                    v.name = n
                columns.append(v)
                columnsByName[v.name] = v.affinity
            else:
                new_attrs[n] = v

        if "indexes" in new_attrs:
            if isinstance(new_attrs["indexes"], list):
                indexes = new_attrs["indexes"]

        table_name = class_name[:class_name.rfind("Table")]
        if table_name != "":
            table_name = table_name[0].lower() + table_name[1:]

        cls = type.__new__(cls, class_name, bases, new_attrs)
        cls.columns = columns
        cls.columnsByName = columnsByName
        if not getattr(cls, 'table_name', None):
            cls.table_name = table_name
        if not getattr(cls, 'server_table_name', None):
            cls.server_table_name = table_name
        return cls


class Table:
    __metaclass__ = TableMeta
    columns = []
    columnsByName = {}
    table_name = ''
    indexes = []
    update = True
    tableVersion = 0

    @classmethod
    def sql(cls):
        """
        Returns SQL statement to create this table
        """
        output = []
        output.append("CREATE TABLE IF NOT EXISTS `%s` (\n%s\n);\n" % (
            cls.table_name,
            ',\n'.join(column.sql() for column in cls.columns)
        ))
        if len(cls.indexes) != 0:
            output.extend(cls.indexes)
        return output


class CommandsTable(Table):
    """
    Defines the commands table. Lists all possible commands a local or remote gateway can perform.
    """
    tableVersion = 20
    table_name = 'commands'
    cmdUUID = TextPKColumn()
    uri = TextColumn()
    machineLabel = TextColumn()
    voiceCmd = TextColumn()
    label = TextColumn()
    description = TextColumn()
    inputTypeUUID = TextColumn()
    liveUpdate = IntegerColumn()
    public = IntegerColumn()
    status = IntegerColumn()
    created = IntegerColumn()
    updated = IntegerColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS machineLabel_idx ON %s (machineLabel);" % (table_name),
               "CREATE INDEX IF NOT EXISTS voicecmd_idx ON %s (voicecmd);" % (table_name)]


class ConfigTable(Table):
    """
    Defines the config table for the local gateway.
    """
    tableVersion = 15
    table_name = 'config'
    configid = IntegerPKColumn()
    configPath = TextColumn()
    configValue = TextColumn()
    configKey = TextColumn()
    updated = IntegerColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS configPath_idx ON %s (configPath);" % (table_name),
               "CREATE INDEX IF NOT EXISTS configkey_idx ON %s (configKey);" % (table_name)]


class DevicesTable(Table):
    """
    Defines the devices table. Lists all possible devices for local gateway and related remote gateways.
    """
    tableVersion = 20
    table_name = 'devices'
    deviceUUID = TextPKColumn()
    uri = TextColumn()
    label = TextColumn()
    description = TextColumn()
    gatewayUUID = TextColumn()
    deviceTypeUUID = TextColumn()
    notes = TextColumn()
    voiceCmd = TextColumn()
    voiceCmdOrder = TextColumn()
    VoiceCmdSrc = TextColumn()
    deviceTypeUUID = TextColumn()  # TODO: Change all references to 'modulelabel'
    pinCode = TextColumn()
    pinRequired = BooleanColumn()
    pinTimeout = IntegerColumn()
    #    liveUpdate = IntegerColumn()
    created = IntegerColumn()
    updated = IntegerColumn()
    status = IntegerColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS deviceTypeUUID_idx ON %s (deviceTypeUUID);" % (table_name)]  # for joins


class DeviceTypesTable(Table):
    """
    Device types defines the features of a device. For example, all X10 appliances or Insteon Lamps.
    """
    tableVersion = 20
    table_name = 'devicetypes'
    deviceTypeUUID = TextPKColumn()
    uri = TextColumn()
    machineLabel = TextColumn()
    label = TextColumn()
    description = TextColumn()
    liveUpdate = IntegerColumn()
    public = IntegerColumn()
    status = IntegerColumn()
    created = IntegerColumn()
    updated = IntegerColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS machineLabel_idx ON %s (machineLabel);" % (table_name)]


class DeviceTypeCommandsTable(Table):
    """
    All possible commands for a given device type. For examples, appliances are on and off.
    """
    tableVersion = 20
    table_name = 'devicetypecommands'
    deviceTypeUUID = TextColumn()
    cmdUUID = TextColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS deviceTypeUUID_idx ON %s (deviceTypeUUID);" % (table_name),
               "CREATE INDEX IF NOT EXISTS cmdUUID_idx ON %s (cmdUUID);" % (table_name)]


class DeviceStatusTable(Table):
    """
    Defines the device status table. Stores device status information.
    """
    tableVersion = 15
    table_name = 'devicestatus'
    rowID = IntegerPKColumn()
    deviceUUID = TextColumn()
    settime = RealColumn()
    status = TextColumn()
    statusExtra = BlobColumn()
    source = TextColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS deviceUUID_idx ON %s (deviceUUID);" % (table_name)]


# class InterfacesTable(Table):
#    table_name = 'interfaces'
#    moduleUUID = TextPKColumn()
#    interfaceUUID = TextColumn()
##    indexes = ["CREATE INDEX IF NOT EXISTS moduleUUID_idx ON %s (moduleUUID);" % (table_name)]


class gwTokensTable(Table):
    """
    User access tokens to login to this gateway directly.

    Note: Not currently implemented.
    """
    tableVersion = 15
    table_name = 'gwTokens'
    gwtokenid = TextPKColumn()
    gwtoken = TextColumn()
    username = TextColumn()
    created = IntegerColumn()
    lastaccess = IntegerColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS gwtokenid_idx ON %s (gwtokenid);" % (table_name)]


class ModulesTable(Table):
    """
    Stores module information
    """
    tableVersion = 20
    table_name = 'modules'
    moduleUUID = TextPKColumn()
    uri = TextColumn()
    moduleType = TextColumn()
    machineLabel = TextColumn()
    label = TextColumn()
    description = TextColumn()
    installNotes = TextColumn()
    docLink = TextColumn()
    installBranch = TextColumn()
    prodVersion = TextColumn()
    devVersion = TextColumn()
    public = IntegerColumn()
    status = IntegerColumn()
    created = IntegerColumn()
    updated = IntegerColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS machineLabel_idx ON %s (machineLabel);" % (table_name)]


class ModuleDeviceTypesTable(Table):
    """
    Maps devices to a module using deviceTypes.
    """
    tableVersion = 20
    table_name = 'moduleDeviceTypes'
    deviceTypeUUID = TextColumn()
    priority = IntegerColumn()
    moduleUUID = TextColumn()
    moduleLabel = TextColumn()
    moduleType = TextColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS deviceTypeUUID_idx ON %s (deviceTypeUUID);" % (table_name),
               "CREATE INDEX IF NOT EXISTS moduleUUID_idx ON %s (moduleUUID);" % (table_name),
               "CREATE INDEX IF NOT EXISTS dt_m_idx ON %s (deviceTypeUUID, moduleUUID);" % (table_name)]


class ModulesInstalledTable(Table):
    """
    Tracks what versions of a module is installed, when it was installed, and last checked for new version.
    """
    tableVersion = 15
    table_name = 'modulesinstalled'
    moduleUUID = TextPKColumn()
    installedVersion = TextColumn()
    installTime = IntegerColumn()
    lastCheck = IntegerColumn()
# indexes = ["CREATE INDEX IF NOT EXISTS moduleUUID_idx ON %s (moduleUUID);" % (table_name)]


class ModuleVariablesTable(Table):
    """
    Stores variables for modules. Variables are set by the server, and read here. Not a two-way sync (yet?).
    """
    tableVersion = 20
    table_name = 'moduleVariables'
    moduleUUID = TextColumn()
    variableUUID = TextColumn()
    weight = IntegerColumn()
    dataWeight = IntegerColumn()
    machineLabel = TextColumn()
    label = TextColumn()
    value = TextColumn()
    updated = IntegerColumn()
    created = IntegerColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS moduleUUID_idx ON %s (moduleUUID);" % (table_name),
               "CREATE INDEX IF NOT EXISTS variableUUID_idx ON %s (variableUUID);" % (table_name)]


class SQLDictTable(Table):
    """
    Defines the SQL Dict table. Used by the :class:`SQLDict` class to maintain
    persistent dictionaries.
    """
    tableVersion = 15
    table_name = 'sqldict'
    rowID = IntegerPKColumn()
    module = TextColumn()
    dictname = TextColumn()
    key1 = TextColumn()
    data1 = BlobColumn()
    created = IntegerColumn()
    updated = IntegerColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS dictname_idx ON %s (dictname);" % (table_name),
               "CREATE INDEX IF NOT EXISTS module_idx ON %s (module);" % (table_name)]


class VariableDevicesTable(Table):
    tableVersion = 15
    table_name = 'variableDevices'
    deviceUUID = TextColumn()
    variableUUID = TextColumn()
    weight = IntegerColumn()
    dataWeight = IntegerColumn()
    varNames = BlobColumn()
    varValues = BlobColumn()
    updated = IntegerColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS deviceUUID_idx ON %s (deviceUUID);" % (table_name)]


class UsersTable(Table):
    tableVersion = 15
    table_name = 'users'
    username = TextPKColumn()
    hash = TextColumn()


# indexes = ["CREATE INDEX IF NOT EXISTS username_idx ON %s (username);" % (table_name)]


class LogsTable(Table):
    tableVersion = 15
    table_name = 'logs'
    rowID = IntegerPKColumn()
    logTime = TextColumn()
    logLine = TextColumn()
    indexes = ["CREATE INDEX IF NOT EXISTS logtime_idx ON %s (logTime);" % (table_name)]


ALLTABLES = [
    CommandsTable,
    ConfigTable,
    DevicesTable,
    DeviceTypesTable,
    DeviceTypeCommandsTable,
    DeviceStatusTable,
    #    InterfacesTable,
    LogsTable,
    gwTokensTable,
    ModulesTable,
    ModuleDeviceTypesTable,
    ModulesInstalledTable,
    ModuleVariablesTable,
    SQLDictTable,
    VariableDevicesTable,
    UsersTable,
]

# these tables can be emptied and redownloaded as needed.
CONFTABLES = [
    CommandsTable,
    DevicesTable,
    DeviceTypesTable,
    DeviceTypeCommandsTable,
    gwTokensTable,
    ModulesTable,
    ModuleDeviceTypesTable,
    ModuleVariablesTable,

    VariableDevicesTable,
    UsersTable,
]


class AllTabless:
    global ALLTABLES
    alltablessss = ALLTABLES

    def __init__(self):
        pass
