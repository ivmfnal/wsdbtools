from __future__ import print_function
import socket, select, threading, time
from pythreader import PyThread, synchronized

class Server:
    
    def __init__(self, host, port, down_timeout):
        self.Host = host
        self.Port = port
        self.IsUp = True
        self.DownUntil = None
        self.DownTimeout = down_timeout     # seconds

    def markDown(self):
        self.IsUp = False
        self.DownUntil = time.time() + self.DownTimeout
        
    def isUp(self):
        if not self.IsUp and self.DownUntil < time.time():    self.IsUp = True
        return self.IsUp
        
    def address(self):
        return self.Host, self.Port

class ServerList:

    def __init__(self, servers, down_timeout):
        self.Servers = [Server(host, port, down_timeout) 
            for host,port in servers]
        self.NextInx = 0

    def getNext(self):
        i = self.NextInx
        s = self.Servers[i]
        found = False
        while not found:
            if s.isUp():  found = True
            else:
                i = (i+1) % len(self.Servers)
                s = self.Servers[i]
            if i == self.NextInx:   found = True
        self.NextInx = (i+1) % len(self.Servers)
        return s
        
    def __len__(self):
        return len(self.Servers)

class Tunnel(PyThread):

    MAXMSG = 100000
        
    def __init__(self, parent, src, dst):
        PyThread.__init__(self)
        self.Src = src
        self.Dst = dst
        self.Parent = parent
        self.Error = None
        self.ByteCount = 0
        
    def run(self):
        closed = False
        while not closed:
            try:    data = self.Src.recv(self.MAXMSG)
            except: 
                data = ""
                self.Error = "%s %s" % sys.exc_info()[:2]
            if not data:
                closed = True
            else:
                self.Dst.send(data)
                self.ByteCount += len(data)
        if closed:
            try:    self.Dst.shutdown(socket.SHUT_WR)
            except: pass
        self.Parent.childDone(self)
            
        
class Connection(PyThread):

    MAXMSG = 100000
        
    def __init__(self, manager, asock, baddr, bsock):
    
        PyThread.__init__(self)

        self.ASock = asock
        self.BSock = bsock
        self.AAddr = asock.getpeername()
        self.BAddr = baddr
        self.Manager = manager
        self.Closed = False
        self.ABBytes = self.BABytes = 0
        self.TStart = time.time()
        self.Elapsed = 0.0

    def run(self):
        
        ab_tunnel = Tunnel(self, self.ASock, self.BSock)
        ba_tunnel = Tunnel(self, self.BSock, self.ASock)
        ab_tunnel.start()
        ba_tunnel.start()
        while not self.Closed:
            self.sleep(10)
        ab_tunnel.join()        # then wait for the other
        ba_tunnel.join()
        self.ASock.close()
        self.BSock.close()
        self.ABBytes = ab_tunnel.ByteCount
        self.BABytes = ba_tunnel.ByteCount
        self.Elapsed = time.time() - self.TStart
        self.Manager.connectionClosed(self)
    
    @synchronized
    def childDone(self, child):
        self.Closed = True
        self.wakeup()
        
class TunnelManager(PyThread):

    def __init__(self, port, servers, down_timeout, quiet):
        PyThread.__init__(self)
        self.ServerList = ServerList(servers, down_timeout)
        self.Port = port
        self.LSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.LSock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.LSock.bind(('', self.Port))
        self.LSock.listen(10)
        self.ActiveConnections = []
        self.Quiet = quiet

    def chooseServer(self):
        done = False
        srv, addr, sock = None, None, None
        for i in range(len(self.ServerList)):
            srv = self.ServerList.getNext()
            addr = srv.address()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect(addr)
            except:
                srv.markDown()
            else:
                done = True
                break
        if done:    return  srv, addr, sock
        else:       return  None, None, None
        
    def run(self):
        while True:
            csock, a = self.LSock.accept()
            srv, addr, ssock = self.chooseServer()
            if ssock == None:
                csock.close()
            else:
                if not self.Quiet: print ("%s: Connected    %s:%s->%s:%s" % (time.ctime(time.time()), a[0], a[1], addr[0], addr[1]))
                conn = Connection(self, csock, addr, ssock)
                self.ActiveConnections.append(conn)
                conn.start()
                
    @synchronized
    def connectionClosed(self, conn):
        if not self.Quiet: print("%s: Disconnected %s:%s->%s:%s, time: %.3f, bytes: %d/%d" % 
				(time.ctime(time.time()), conn.AAddr[0], conn.AAddr[1], conn.BAddr[0], conn.BAddr[1], 
				conn.Elapsed,
				conn.ABBytes, conn.BABytes))
        if conn in self.ActiveConnections:
            self.ActiveConnections.remove(conn)

Usage = """
python tcp_tunnel.py [-q] <tunnel port> <server host>:<server_port> [...]
"""

if __name__ == '__main__':
    import sys, getopt

    opts, args = getopt.getopt(sys.argv[1:], "q")
    opts = dict(opts)

    if not args:
        print (Usage)
        sys.exit(2)

    quiet = "-q" in opts
    
    port = int(args[0])
    servers = [(a, int(p)) for a, p in 
                    [w.split(":",1) for w in args[1:]]]
    tt = TunnelManager(port, servers, 10, quiet)
    tt.run()
    tt.join()
            
    
