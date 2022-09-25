from webpie import WPApp, WPHandler, Response
import os, time, random
from datetime import datetime, timedelta
 
 
def parseRelPath(relpath):
        if not relpath: return {}
        dct = {}
        for w in relpath.split("/"):
            w = w.strip()
            if w:
                words = w.split("=", 1)
                name = words[0].strip()
                if name:
                    value = None
                    if len(words) > 1:
                        value = words[1]
                        try:    value = int(value)
                        except:
                            try:    value = float(value)
                            except:
                                pass
                    dct[name] = value
        return dct
       

def merge_relpath(method):
    def new_method(self, req, relpath, **args):
        dct = parseRelPath(relpath)
        #print dct
        dct.update(args)
        #print dct
        return method(self, req, **dct)
        
    return new_method

class EchoHandler(WPHandler):

    @merge_relpath
    def probe(self, req, error_rate=None, error_code=500,
            delay=None, min_delay=None, max_delay=None, 
            error_after_delay=False, **args):
        #print error_rate
        if delay != None:   delay = float(delay)
        if delay == None:
            if min_delay != None:
                min_delay = float(min_delay)
                max_delay = float(max_delay)
                delay = min_delay + random.random()*(max_delay - min_delay)
        if not delay:   delay = 0.0
        if error_rate != None:  error_rate = float(error_rate)
        if not error_rate:  error_rate = 0.0

        error_after_delay = error_after_delay and (error_after_delay != 'no')
        
        if error_after_delay:
            if delay:   time.sleep(delay)
        
        if random.random() < error_rate:
            resp = Response("Error", status=int(error_code))
            return resp
        
        if not error_after_delay:
            if delay:   time.sleep(delay)
            
        return Response("OK", cache_control="no-store, no-cache")



    def mergeLines(self, iter, maxlen=50):
        buf = []
        total = 0
        for l in iter:
            n = len(l)
            if n + total > maxlen:
                yield ''.join(buf)
                buf = []
                total = 0
            buf.append(l)
            total += n
        if buf:
            yield ''.join(buf)
        
    def data_generator(self, columns, rows, pre_delay = 0, mid_delay = 0, post_delay = 0):
        if pre_delay:   time.sleep(pre_delay)
        yield ','.join(columns) + '\n'
        nc = len(columns)
        for r in range(rows):
            row = ','.join(['%s' % (random.random(),) for x in columns]) + '\n'
            if mid_delay and r == rows/2:
                time.sleep(mid_delay)
            yield row
        if post_delay:  time.sleep(post_delay)
            
    @merge_relpath
    def incomplete(self, req, length=1024, stop=512, **args):
        length = int(length)
        stop = int(stop)
        
        txt = "x,y\n"
        while len(txt) < stop:
            txt += "1,2\n"
        
        resp = Response(app_iter=txt, 
            content_type='text/plain',content_length = length)
        #print "length=",length
        return resp

    def generate_chunks(self, error):
        yield "10\r\n1234567890123456\r\n"
        yield "10\r\n1234567890123456\r\n"
        if error:
            yield "10\r\n1234567"
        else:
            yield "0\r\n\r\n"
        
    @merge_relpath
    def chunked_incomplete(self, req, short="no", **args):
        error = short == 'yes'
        
        data = self.generate_chunks(error)
        resp = Response(app_iter=data, 
            content_type='text/plain'
            )
        #print list(data)
        resp.headers.add("Transfer-Encoding","chunked")
        #print "length=",length
        return resp

    @merge_relpath
    def data(self, req, error_rate=None, error_code=500,
            columns="x,y",
            rows=None, delay=None, min_delay=None, max_delay=None, 
            error_after_delay=False, cache = None,
            pre_delay = 0, mid_delay = 0, post_delay = 0,
            **args):
            
        pre_delay = int(pre_delay)
        post_delay = int(post_delay)
        mid_delay = int(mid_delay)

        if delay != None:   delay = float(delay)
        if delay == None:
            if min_delay != None:
                min_delay = float(min_delay)
                max_delay = float(max_delay)
                delay = min_delay + random.random()*(max_delay - min_delay)
        if not delay:   delay = 0.0
        if error_rate != None:  error_rate = float(error_rate)
        if not error_rate:  error_rate = 0.0

        error_after_delay = error_after_delay and (error_after_delay != 'no')
        
        if error_after_delay:
            if delay:   time.sleep(delay)
        
        if random.random() < error_rate:
            resp = Response("Error", status=int(error_code))
            return resp
        
        if not error_after_delay:
            if delay:   time.sleep(delay)
        

        if rows != None:    rows = int(rows)
        if not rows:    rows = 10
        columns = columns.split(',')

            
        #resp = Response(app_iter = 
        #    self.mergeLines(
        #                pre_delay, mid_delay, post_delay), 10000),
        #    content_type='text/plain'
        #    #,cache_control="max-age=80"
        #    ) 
        headers = {
            "Content-Type":'text/csv'
        }
        if cache != None:
            headers["Cache-Control"] = "max-age=%s" % (cache,)
        return (
            self.data_generator(columns, rows, 
                        pre_delay, mid_delay, post_delay),
            200,
            headers
        )

    @merge_relpath
    def post(self, req, delay=None, min_delay=None, max_delay=None, **args):
        if delay != None:   delay = float(delay)
        if delay == None:
            if min_delay != None:
                min_delay = float(min_delay)
                max_delay = float(max_delay)
                delay = min_delay + random.random()*(max_delay - min_delay)
        if not delay:   delay = 0.0
        time.sleep(delay)
        resp = Response("OK %s" % (len(req.body),), content_type='text/plain')
        return resp
       
    def echo(self, req, rel_path, **args):
        if req.method.upper in ("POST","PUT"):
            resp = Response("%s" % (req.body,), content_type='text/plain')
            return resp
        else:
            return rel_path or "echo", 200, "text/plain"
       
application = WPApp(EchoHandler)  

if __name__ == '__main__':
    print("Starting server at port 8081")
    application.run_server(8081)
    
    
