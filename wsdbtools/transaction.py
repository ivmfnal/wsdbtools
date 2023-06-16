class Transaction(object):
    
    def __init__(self, connection, on_delete="commit"):
        assert not on_delete or on_delete in ("commit", "rollback")
        self.Connection = connection
        self.Cursor = self.Connection.cursor()
        self.InTransaction = False
        self.Exc = None
        self.Failed = False
        self.OnDelete = on_delete

    def begin(self):
        self.Cursor.execute("begin")
        self.InTransaction = True
        
    def commit(self):
        self.Cursor.execute("commit")
        self.InTransaction = False
        
    def rollback(self):
        self.Cursor.execute("rollback")
        self.InTransaction = False
        
    def execute(self, *params, **args):
        if not self.InTransaction:
            raise RuntimeError("Not in transaction")
        try:
            self.Cursor.execute(*params, **args)
        except:
            self.rollback()
            raise

    def __enter__(self):
        self.begin()
        return self
        
    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self.Exc = (exc_type, exc_value, traceback)
            self.rollback()
        #else:  do not do commit here. Do it in the __del__ method instead
        #    self.commit()
            
    def __getattr__(self, name):
        return getattr(self.Cursor, name)
        
    def cursor_iterator(self):
        while True:
            tup = self.Cursor.fetchone()
            if tup is None:
                break
            yield tup

    def __iter__(self):
        return self.cursor_iterator()
        
    def __del__(self):
        #print("Transaction __del__")
        if self.InTransaction:
            if self.OnDelete == "commit":
                self.commit()
            elif self.OnDelete == "rollback":
                self.rollback()
            