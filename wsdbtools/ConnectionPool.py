import time
from threading import RLock, Thread
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
        #print("_WrappedConnection: __del__()...")
        self._done()
        #print("_WrappedConnection: __del__()")
    
    def close(self):
        if self.Connection is not None:
            self.Connection.close()
            self.Connection = None
            self.Pool = None

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

    Lock = RLock()
    Count = 0
    NextID = 1

    def __init__(self):
        with DummyConnection.Lock:
            DummyConnection.Count += 1
            self.ID = DummyConnection.NextID
            DummyConnection.NextID += 1

        #print ("Connection created: >> %s" % (self,))

    def __str__(self):
        return "<connection %d>" % (self.ID,)
        
    def close(self):
        #print ("Connection closed:  << %s" % (self,))
        with self.Lock:
            DummyConnection.Count -= 1
        

class DummyConnector(ConnectorBase):

    def connect(self):
        return DummyConnection()
        
    def probe(self, connection):
        return True
        
    def connectionIsClosed(self, connection):
        return False

class PsycopgConnector(ConnectorBase):

    def __init__(self, connstr):
        ConnectorBase.__init__(self)
        self.Connstr = connstr
        
    def connect(self):
        import psycopg2
        return psycopg2.connect(self.Connstr)
        
    def connectionIsClosed(self, conn):
        return conn.closed
        
    def probe(self, conn):
        try:
            c = conn.cursor()
            c.execute("rollback; select 1")
            alive = c.fetchone()[0] == 1
            c.execute("rollback")
            return alive
        except:
            return False
            
class MySQLConnector(ConnectorBase):
    def __init__(self, connstr):
        raise NotImplementedError
        
              
class ConnectionPool(PyThread):      

    def __init__(self, postgres=None, mysql=None, connector=None, 
                idle_timeout = 30, max_idle_connections = 1):
        my_name = "ConnectionPool"
        if postgres:
            keep_words = sorted([w for w in postgres.split() if not (w.startswith("password=") or w.startswith("user=")])
            my_name = "ConnectionPool(postgres:%s)" % (" ".join(keep_words),)
        PyThread.__init__(self, name=my_name, daemon=True)
        self.IdleTimeout = idle_timeout
        if connector is not None:
            self.Connector = connector
        elif postgres is not None:
            self.Connector = PsycopgConnector(postgres)
        elif mysql is not None:
            self.Connector = MySQLConnector(mysql)
        else:
            raise ValueError("Connector must be provided")
        self.IdleConnections = []           # [_IdleConnection(c), ...]
        self.Lock = RLock()
        self.MaxIdleConnections = max_idle_connections
        self.Closed = False
        self.start()
        
    def close_idle(self):
        with self.Lock:
            for ic in self.IdleConnections:
                ic.Connection.close()
            self.IdleConnections = []

    def clean_up(self):
        with self.Lock:
            now = time.time()
            #print("cleanUp: idle connections: %d %x %s" % (len(self.IdleConnections), id(self.IdleConnections), self.IdleConnections))
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

    def run(self):
        while not self.Closed:
            time.sleep(self.IdleTimeout/5)
            self.clean_up()

    def idleCount(self):
        with self.Lock:
            return len(self.IdleConnections)

    def connect(self):
        with self.Lock:
            if self.Closed:
                raise RuntimeError("Connection pool is closed")
            use_connection = None
            #print "connect(): Connections=", self.IdleConnections
            while self.IdleConnections:
                c = self.IdleConnections.pop().Connection
                if self.Connector.probe(c):
                    use_connection = c
                    #print ("connect: reuse idle connection %s" % (c,))
                    break
                else:
                    c.close()       # connection is bad
            else:
                # no connection found
                use_connection = self.Connector.connect()
                #print ("connect: new connection %s" % (use_connection,))
            return _WrappedConnection(self, use_connection)

    def cursor(self):
        return self.connect().cursor()
        
    def transaction(self):
        return self.connect().transaction()
        
    txn = transaction

    def returnConnection(self, c):
        #print("returnConnection() ...")
        if not self.Connector.connectionIsClosed(c):
            with self.Lock:
                if len(self.IdleConnections) >= self.MaxIdleConnections or self.Closed:
                    c.close()
                elif all(c is not x.Connection for x in self.IdleConnections):
                    self.IdleConnections.append(_IdleConnection(c))
        #print("returnConnection() exit")

    def close(self):
        with self.Lock:
            self.Closed = True
            self.close_idle()
            
    def __del__(self):
        self.close()

if __name__ == "__main__":
    #
    # test
    #
    import time, random
    
    class DummyConnection(object):
    
        Lock = RLock()
        Count = 0
    
        def __init__(self):
            print ("Connection created: >> %x" % (id(self),))
            with self.Lock:
                DummyConnection.Count += 1
            
        def close(self):
            print ("Connection closed:  << %x" % (id(self),))
            with self.Lock:
                DummyConnection.Count -= 1
            
    
    class DummyConnector(ConnectorBase):
    
        def connect(self):
            return DummyConnection()
            
        def probe(self, connection):
            return True
            
        def connectionIsClosed(self, connection):
            return False
            
    class Client(Thread):
    
        def __init__(self, pool):
            Thread.__init__(self)
            self.Pool = pool
    
        def run(self):
            for _ in range(10):
                time.sleep(random.random()*1.0)
                c = pool.connect()
                time.sleep(random.random()*1.0)
                #c.close()
            print ("thread is done")
    
    pool = ConnectionPool(connector=DummyConnector(), idle_timeout = 5)
    
    clients = [Client(pool) for _ in range(5)]
    for c in clients:
        c.start()
        
    t0 = time.time()
    
    while True:
        print ("idle count:", pool.idleCount(), "     open count:", DummyConnection.Count)
        time.sleep(3)
    
    
    
    
    
    
