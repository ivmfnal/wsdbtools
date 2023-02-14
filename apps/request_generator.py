from pythreader import TaskQueue, Task, PyThread, Primitive, synchronized
import sys, getopt, time
import requests

Usage = """
python request_generator.py [-r <rate/second>] [-m <max threads>] <url>
"""

Usage = """
python request_generator.py -m <max threads> -r <rate> <url>
"""

class FrequencyMeter(Primitive):

    def __init__(self):
        Primitive.__init__(self)
        self.Record = []
        
    @synchronized
    def tick(self):
        now = time.time()
        self.Record.append(now)
        self.purge()
        
    @synchronized
    def purge(self):
        i = 0
        now = time.time()
        for i, t in enumerate(self.Record):
            if t >= now - 10.0:
                break
        self.Record = self.Record[i:]
        
    @synchronized
    def frequency(self):
        self.purge()
        if len(self.Record) < 2 or self.Record[-1] == self.Record[0]: return 0
        return len(self.Record)/(self.Record[-1]-self.Record[0])

opts, args = getopt.getopt(sys.argv[1:], "r:m:")
opts = dict(opts)

if not args:
    print (Usage)
    sys.exit(2)

url = args[0]

rate = opts.get("-r")
stagger = None if rate is None else 1.0/float(rate)
num_threads = int(opts.get("-m", 1))

q = TaskQueue(num_threads, stagger=stagger, capacity=num_threads*10)

class Request(Task):

    def __init__(self, url, meter):
        Task.__init__(self)
        self.URL = url
        self.Meter = meter

    def run(self):
        try:	
            resp = requests.get(self.URL)
            status = resp.status_code
            size = len(resp.text)
            print(self.URL, status, size)
        except Exception as e:
            print(e)
        self.Meter.tick()

meter = FrequencyMeter()
next_report = time.time() + 5        
n = 0
while True:
    u = url
    q << Request(u, meter)
    n += 1
    if time.time() > next_report:
        print("Requests: %d Frequency: %.3f" % (n,meter.frequency()))
        next_report = time.time() + 5        
    


