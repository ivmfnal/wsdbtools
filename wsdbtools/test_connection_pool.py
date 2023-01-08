from ConnectionPool import ConnectionPool

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
    
    
    
    
    
    
