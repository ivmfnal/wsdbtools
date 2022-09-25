import re, hashlib, requests, base64, time
from requests.auth import HTTPDigestAuth

def digest_client(url, username, password):
    response = requests.get(url, auth=HTTPDigestAuth(username, password))
    return response.status_code, response.content

def digest_server(realm, env, get_password):
    #
    # Server side authentication function
    # env is WSGI evironment
    # get_password is a function: password = get_password(realm, username)
    # 

    def md5sum(data):
        from hashlib import md5
        m = md5()
        if isinstance(data, str):
            data = data.encode("utf-8")
        m.update(data)
        return m.hexdigest()

    auth_header = env.get("HTTP_AUTHORIZATION","")
    #print "auth_header:", auth_header
    matches = re.compile('Digest \s+ (.*)', re.I + re.X).match(auth_header)
    
    
    if not matches:
        # need "Authorization" header
        nonce = base64.b64encode(str(int(time.time())).encode("utf-8"))
        header = 'Digest realm="%s", nonce="%s", algorithm=MD5, qop="auth"' % (realm, nonce)
        return False, header        
    
    
    vals = re.compile(', \s*', re.I + re.X).split(matches.group(1))

    dict = {}

    pat = re.compile('(\S+?) \s* = \s* ("?) (.*) \\2', re.X)
    for val in vals:
        ms = pat.match(val)
        if ms:
            dict[ms.group(1)] = ms.group(3)

    user = dict['username']
    cfg_password = get_password(realm, user)
    if cfg_password == None:
        # unknown user
        return False, None

    a1 = md5sum('%s:%s:%s' % (user, realm, cfg_password))        
    a2 = md5sum('%s:%s' % (env['REQUEST_METHOD'], dict["uri"]))
    myresp = md5sum('%s:%s:%s:%s:%s:%s' % (a1, dict['nonce'], dict['nc'], dict['cnonce'], dict['qop'], a2))
    if myresp == dict['response']:
        # success
        return True, user
    else:
        # password did not match
            #print "signature mismatch"
        return False, None

if __name__ == "__main__":

        from webpie import WPApp, WPHandler, Response

        class H(WPHandler):

                def get_password(self, realm, user):
                        return "secret"

                def access(self, request, relpath, **args):
                        passed, header = digest_server("", request.environ, self.get_password)
                        if passed:
                                return "Access granted\n"
                        else:
                                if header:
                                        return "Authorization required", 401, {
                                                'WWW-Authenticate': header
                                            }   
                                else:
                                        return "Access denied", 403

        WPApp(H).run_server(8881)
