import time
from pythreader import Primitive, schedule_task, synchronized, version_info as pythreader_version
assert pythreader_version >= (2,11,0), f"pythreader version >= 2.11.0 is required. Installed: {pythreader_version}"

from .transaction import Transaction

class _WrappedCursor(object):
    #
    # this wrapper is needed to keep the pointer to the _WrappedConnection to keep its ref count
    # from going to zero
    #

    def __init__(self, wrapped_connection, real_cursor):
        self.RealCursor = real_cursor
        self.WrappedConnection = wrapped_connection

    #
    # forward everything to the real cursor
    #
    def __getattr__(self, name):
        return getattr(self.RealCursor, name)

class _WrappedConnection(object):
    #
    # The pool can be used in 2 ways:
    #
    # 1. explicit connection
    #   
    #   conn = pool.connect()
    #   ....
    #   conn.close()
    #
    #   conn = pool.connect()
    #   ...
    #   # connection goes out of scope and closed during garbage collection
    #
    # 2. via context manager
    #
    #   with pool.connect() as conn:
    #       ...
    #

    def __init__(self, pool, connection):
        self.Connection = connection
        self.Pool = pool
        
    def __str__(self):
        return "WrappedConnection(%s)" % (self.Connection,)

    def _done(self):
        #print("_WrappedConnection: _done()")
        if self.Pool is not None:
            self.Pool.returnConnection(self.Connection)
            self.Pool = None
        if self.Connection is not None:
            self.Connection = None
    
    #
    # If used via the context manager, unwrap the connection
    #
    def __enter__(self):
        return self.Connection
        
    def __exit__(self, exc_type, exc_value, traceback):
        self._done()

    def transaction(self, *params, **kw):
        return Transaction(self, *params, **kw)

    txn = transaction       # synonym

    #
    # If used as is, instead of deleting the connection, give it back to the pool
    #
    def __del__(self):
        self._done()
    
    def close(self):
        if self.Connection is not None:
            self.Connection.close()
            self.Pool.returnConnection(self.Connection)     # return even if it is closed, just to update counts
            self.Connection = self.Pool = None

    def cursor(self):
        # link the cursor back to the connection wrapper so the wrapper does not get deleted as long as at least one cursor is still active
        c = _WrappedCursor(self, self.Connection.cursor())
        return c
    
    #
    # act as a database connection object
    #
    def __getattr__(self, name):
        return getattr(self.Connection, name)

class _IdleConnection(object):
    def __init__(self, conn):
        self.Connection = conn          # db connection
        self.IdleSince = time.time()

class ConnectorBase(object):

    def connect(self):
        raise NotImplementedError
        
    def probe(self, connection):
        return True
        
    def connectionIsClosed(self, c):
        raise NotImplementedError
        
class DummyConnection(object):
    
    Counter = 0

    def __init__(self):
        DummyConnection.Counter += 1
        self.Closed = False
        
    def close(self):
        if not self.Closed:
            DummyConnection.Counter -= 1
            self.Closed = True

    def __del__(self):
        self.close()

class DummyConnector(ConnectorBase, Primitive):
    
    # used for debugging
    
    def __init__(self, max_connections):
        Primitive.__init__(self)
        self.MaxConnections = max_connections
    
    @synchronized
    def connect(self):
        if DummyConnection.Counter >= self.MaxConnections:
            raise RuntimeError("Would exceed the connection limit")
        return DummyConnection()
    
    def probe(self, connection):
        return not connection.Closed
    
    def connectionIsClosed(self, connection):
        return connection.Closed

class PsycopgConnector(ConnectorBase):

    def __init__(self, connspec, schema=None):
        ConnectorBase.__init__(self)
        if isinstance(connspec, dict):
            if "url" in connspec:
                self.Connstr = connspec["url"]
            else:
                parts = [
                    "%s=%s" % (key, connspec[key]) 
                    for key in ["host", "port", "password", "dbname", "user"]
                    if key in connspec
                ]
                self.Connstr = " ".join(parts)
            schema = schema or connspec.get("schema")
        else:
            # assume str
            self.Connstr = connspec
        self.Schema = schema
    
    def connect(self):
        import psycopg2
        conn = psycopg2.connect(self.Connstr)
        if self.Schema:
            try:
                # psycopg opens new transaction once new connection is created
                # this transaction has to be closed so that the following "set schema" has "global" effect
                conn.rollback()         
            except:
                pass
            conn.cursor().execute(f"set session schema '{self.Schema}'")
        return conn
        
    def connectionIsClosed(self, conn):
        return conn.closed
        
    def probe(self, conn):

        try:
            # roll back unfinished transaction, if any, and ignore any errors
            conn.rollback()
        except:
            pass

        try:
            # check if the transaction is alive
            c = conn.cursor()
            c.execute("select 1")
            alive = c.fetchone()[0] == 1

            # make sure to set the right schema
            if alive and self.Schema:
                c.execute(f"set session schema '{self.Schema}'")
            return alive
        except Exception as e:
            #print("probe: exception:", e)
            return False
            
class MySQLConnector(ConnectorBase):
    def __init__(self, connstr, schema=None):
        raise NotImplementedError

class ConnectionPool(Primitive):      

    def __init__(self, postgres=None, mysql=None, connector=None, dummy=None,
                idle_timeout=30, max_idle_connections=1, schema=None, max_connections=None):
        my_name = "ConnectionPool"
        Primitive.__init__(self, name=my_name)
        self.IdleTimeout = idle_timeout
        if connector is not None:
            self.Connector = connector
        elif dummy is not None:                     # used for debugging
            self.Connector = DummyConnector(dummy)
        elif postgres is not None:
            self.Connector = PsycopgConnector(postgres, schema)
        elif mysql is not None:
            self.Connector = MySQLConnector(mysql, schema)
        else:
            raise ValueError("Connector must be provided")
        self.IdleConnections = []           # [_IdleConnection(c), ...]
        self.MaxIdleConnections = max_idle_connections
        self.Closed = False
        self.CleanUpJob = schedule_task(self.clean_up, interval=self.IdleTimeout/5)
        self.CheckedOutConnections = 0
        self.MaxConnections = max_connections

    @property
    @synchronized
    def open_connections_count(self):
        return self.CheckedOutConnections + len(self.IdleConnections)

    @synchronized
    def close_idle(self):
        for ic in self.IdleConnections:
            ic.Connection.close()
        self.IdleConnections = []

    @synchronized
    def clean_up(self):
        now = time.time()
        new_list = []
        for ic in self.IdleConnections:
            t = ic.IdleSince
            c = ic.Connection
            if t < now - self.IdleTimeout:
                #print ("closing idle connection %x" % (id(c),))
                c.close()
            else:
                new_list.append(ic)
        self.IdleConnections = new_list

    def idleCount(self):
        return len(self.IdleConnections)

    @synchronized
    def get_idle_connection(self):
        while self.IdleConnections:
            c = self.IdleConnections.pop().Connection
            if self.Connector.probe(c):
                return c
            else:
                c.close()       # connection is bad
        return None

    @synchronized
    def connect(self, timeout=None):
        if self.Closed:
            raise RuntimeError("Connection pool is closed")
        use_connection = self.get_idle_connection()
        while use_connection is None \
                and self.MaxConnections is not None and self.CheckedOutConnections >= self.MaxConnections:
            if use_connection is None:
                self.sleep(timeout)
            if self.Closed:
                raise RuntimeError("Connection pool is closed")
            use_connection = self.get_idle_connection()
        if use_connection is None:
            use_connection = self.Connector.connect()
        self.CheckedOutConnections += 1
        return _WrappedConnection(self, use_connection)

    def cursor(self):
        return self.connect().cursor()

    def transaction(self):
        return self.connect().transaction()

    txn = transaction

    @synchronized
    def returnConnection(self, c):
        self.CheckedOutConnections -= 1
        if not self.Connector.connectionIsClosed(c):
            #print("returnConnection: idle connections:", len(self.IdleConnections))
            if len(self.IdleConnections) >= self.MaxIdleConnections or self.Closed:
                c.close()
            elif all(c is not x.Connection for x in self.IdleConnections):
                self.IdleConnections.append(_IdleConnection(c))
        self.wakeup()

    @synchronized
    def close(self):
        self.Closed = True
        self.close_idle()
        self.CleanUpJob.cancel()

    def __del__(self):
        self.close()

