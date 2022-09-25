import random, time, csv
from urllib import request, URLError, HTTPError

class WDAError(Exception):
    def __init__(self, code, reason, text):
        self.Code = code
        self.Reason = reason
        self.Text = text

class WDAClient(object):

    def getBLOB_file(self, url, timeout=0, first_retry=1.0):
        t1 = None if timeout is None else time.time() + timeout
        retry_interval = float(first_retry)
        max_retry = first_retry * 100
        done = False
        exception = None
        while timeout is None or time.time() < t1:
            do_retry = False
            try:    response = urllib.urlopen(url)
            except HTTPError as http_error:
                do_retry = http_error.code / 100 == 5
                exception = WDAError(http_error.code, http_error.reason,
                    http_error.read())
            else:
                code = response.getcode()
                if code/100 == 2:
                    return response
                exception = WDAError(code, "", response.read())
                do_retry = code/100 == 5
            
            if not do_retry:
                break
            time.sleep(random.random(retry_interval))
            retry_interval = min(max_retry,  retry_interval*1.5)
        if exception:
            raise exception
        return None
        
    def getBLOB_bytes(self, url, timeout=0, first_retry=1.0):
        f = self.getBLOB_file(url, timeout, first_retry)
        if f is not None:
            return f.read()
        else:
            return None
    
        
    def getCSV_iter(self, url, timeout=0, first_retry=1.0, delimiter=','):
        def cvt(x):
            if len(x) == 0: return None
            try:    x=int(x)
            except:
                try:    x=float(x)
                except: pass
        f = self.getBLOB_file(url, timeout, first_retry)
        reader = csv.reader(f, delimiter=delimiter, newline='')
        for row in reader:
            tup = tuple([cvt(x) for x in row])
            yield tup
            
    def getCSV(self, url, timeout=0, first_retry=1.0, delimiter=','):
        return list(self.getCSV_iter(url, timeout, first_retry, delimiter))

        
        
                
            
                    
                
                
                
                
        
        
        
