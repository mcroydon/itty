"""
The itty-bitty Python web framework.

Totally ripping off Sintra, the Python way. Very useful for small applications,
especially web services. Handles basic HTTP methods (PUT/DELETE too!). Errs on
the side of fun and terse.


Example Usage::

    from itty import get, run_itty

      @get('/')
      def index(request):
          return 'Hello World!'

      run_itty()


A couple of bits have been borrowed from other sources:

* Django
  * HTTP_MAPPINGS
* Armin Ronacher's blog (http://lucumr.pocoo.org/2007/5/21/getting-started-with-wsgi)
  * How to get started with WSGI


Thanks go out to Matt Croydon & Christian Metts for putting me up to this late
at night. The joking around has become reality. :)
"""
import re


__author__ = 'Daniel Lindsley'
__version__ = ('0', '1', '0')
__license__ = 'MIT'


REQUEST_MAPPINGS = {
    'GET': [],
    'POST': [],
    'PUT': [],
    'DELETE': [],
}

ERROR_HANDLERS = {}

HTTP_MAPPINGS = {
    100: '100 CONTINUE',
    101: '101 SWITCHING PROTOCOLS',
    200: '200 OK',
    201: '201 CREATED',
    202: '202 ACCEPTED',
    203: '203 NON-AUTHORITATIVE INFORMATION',
    204: '204 NO CONTENT',
    205: '205 RESET CONTENT',
    206: '206 PARTIAL CONTENT',
    300: '300 MULTIPLE CHOICES',
    301: '301 MOVED PERMANENTLY',
    302: '302 FOUND',
    303: '303 SEE OTHER',
    304: '304 NOT MODIFIED',
    305: '305 USE PROXY',
    306: '306 RESERVED',
    307: '307 TEMPORARY REDIRECT',
    400: '400 BAD REQUEST',
    401: '401 UNAUTHORIZED',
    402: '402 PAYMENT REQUIRED',
    403: '403 FORBIDDEN',
    404: '404 NOT FOUND',
    405: '405 METHOD NOT ALLOWED',
    406: '406 NOT ACCEPTABLE',
    407: '407 PROXY AUTHENTICATION REQUIRED',
    408: '408 REQUEST TIMEOUT',
    409: '409 CONFLICT',
    410: '410 GONE',
    411: '411 LENGTH REQUIRED',
    412: '412 PRECONDITION FAILED',
    413: '413 REQUEST ENTITY TOO LARGE',
    414: '414 REQUEST-URI TOO LONG',
    415: '415 UNSUPPORTED MEDIA TYPE',
    416: '416 REQUESTED RANGE NOT SATISFIABLE',
    417: '417 EXPECTATION FAILED',
    500: '500 INTERNAL SERVER ERROR',
    501: '501 NOT IMPLEMENTED',
    502: '502 BAD GATEWAY',
    503: '503 SERVICE UNAVAILABLE',
    504: '504 GATEWAY TIMEOUT',
    505: '505 HTTP VERSION NOT SUPPORTED',
}


class RequestError(Exception):
    """A base exception for HTTP errors to inherit from."""
    status = 404

class NotFound(RequestError):
    status = 404

class AppError(RequestError):
    status = 500

class Redirect(RequestError):
    """
    Redirects the user to a different URL.
    
    Slightly different than the other HTTP errors, the Redirect is less
    'OMG Error Occurred' and more 'let's do something exceptional'. When you
    redirect, you break out of normal processing anyhow, so it's a very similar
    case."""
    status = 302
    url = ''
    
    def __init__(self, url):
        self.url = url


class Request(object):
    """An object to wrap the environ bits in a friendlier way."""
    GET = {}
    POST = {}
    PUT = {}
    
    def __init__(self, environ):
        self._environ = environ
        self.setup_self()
    
    def setup_self(self):
        self.path = add_slash(self._environ.get('PATH_INFO', ''))
        self.method = self._environ.get('REQUEST_METHOD', 'GET').upper()
        self.query = self._environ.get('QUERY_STRING', '')
        self.content_length = 0
        
        try:
            self.content_length = int(self._environ.get('CONTENT_LENGTH', '0'))
        except ValueError:
            pass
        
        self.GET = build_query_dict(self.query)
        
        if self._environ.get('CONTENT_TYPE', '').startswith('multipart'):
            raise Exception("Sorry, uploads are not supported.")
        
        raw_data = ''
        
        if self.content_length != 0:
            raw_data = self._environ['wsgi.input'].read(self.content_length)
        
        if self.method == 'POST':
            self.POST = build_query_dict(raw_data)
        elif self.method == 'PUT':
            self.PUT = build_query_dict(raw_data)


def build_query_dict(query_string):
    """
    Takes GET/POST data and rips it apart into a dict.
    
    Expects a string of key/value pairs (i.e. foo=bar&moof=baz).
    """
    pairs = query_string.split('&')
    query_dict = {}
    pair_re = re.compile('^(?P<key>[^=]*?)=(?P<value>.*)')
    
    for pair in pairs:
        match = pair_re.search(pair)
        
        if match is not None:
            match_data = match.groupdict()
            query_dict[match_data['key']] = match_data['value']
    
    return query_dict


def handle_request(environ, start_response):
    """The main handler. Dispatches to the user's code."""
    request = Request(environ)
    
    try:
        (re_url, url, callback), kwargs = find_matching_url(request)
        output = callback(request, **kwargs)
    except Exception, e:
        return handle_error(e, environ, start_response)
    
    ct = 'text/html'
    status = 200
    
    try:
        ct = callback.content_type
    except AttributeError:
        pass
    
    try:
        status = callback.status
    except AttributeError:
        pass
    
    start_response(HTTP_MAPPINGS.get(status), [('Content-Type', ct)])
    return output


def handle_error(exception, environ, start_response):
    """If an exception is thrown, deal with it and present an error page."""
    environ['wsgi.errors'].write("Exception occurred on '%s': %s\n" % (environ['PATH_INFO'], exception[0]))
    
    if isinstance(exception, RequestError):
        status = getattr(exception, 'status', 404)
    else:
        status = 500
    
    if status in ERROR_HANDLERS:
        return ERROR_HANDLERS[status](exception, environ, start_response)
    
    return not_found(exception, environ, start_response)


def find_matching_url(request):
    """Searches through the methods who've registed themselves with the HTTP decorators."""
    if not request.method in REQUEST_MAPPINGS:
        raise NotFound("The HTTP request method '%s' is not supported." % request.method)
    
    for url_set in REQUEST_MAPPINGS[request.method]:
        match = url_set[0].search(request.path)
        
        if match is not None:
            return (url_set, match.groupdict())
    
    raise NotFound("Sorry, nothing here.")


def add_slash(url):
    """Adds a trailing slash for consistency in urls."""
    if not url.endswith('/'):
        url = url + '/'
    return url


# Decorators

def get(url):
    """Registers a method as capable of processing GET requests."""
    def wrapped(method):
        def new(*args, **kwargs):
            return method(*args, **kwargs)
        # Register.
        re_url = re.compile("^%s$" % add_slash(url))
        REQUEST_MAPPINGS['GET'].append((re_url, url, new))
        return new
    return wrapped


def post(url):
    """Registers a method as capable of processing POST requests."""
    def wrapped(method):
        def new(*args, **kwargs):
            return method(*args, **kwargs)
        # Register.
        re_url = re.compile("^%s$" % add_slash(url))
        REQUEST_MAPPINGS['POST'].append((re_url, url, new))
        return new
    return wrapped


def put(url):
    """Registers a method as capable of processing PUT requests."""
    def wrapped(method):
        def new(*args, **kwargs):
            return method(*args, **kwargs)
        # Register.
        re_url = re.compile("^%s$" % add_slash(url))
        REQUEST_MAPPINGS['PUT'].append((re_url, url, new))
        new.status = 201
        return new
    return wrapped


def delete(url):
    """Registers a method as capable of processing DELETE requests."""
    def wrapped(method):
        def new(*args, **kwargs):
            return method(*args, **kwargs)
        # Register.
        re_url = re.compile("^%s$" % add_slash(url))
        REQUEST_MAPPINGS['DELETE'].append((re_url, url, new))
        return new
    return wrapped


def error(code):
    """Registers a method for processing errors of a certain HTTP code."""
    def wrapped(method):
        def new(*args, **kwargs):
            return method(*args, **kwargs)
        # Register.
        ERROR_HANDLERS[code] = new
        return new
    return wrapped


# Error handlers

@error(404)
def not_found(exception, environ, start_response):
    start_response(HTTP_MAPPINGS[404], [('Content-Type', 'text/plain')])
    return ['Not Found']


@error(500)
def app_error(exception, environ, start_response):
    start_response(HTTP_MAPPINGS[500], [('Content-Type', 'text/plain')])
    return ['Application Error']


@error(302)
def redirect(exception, environ, start_response):
    start_response(HTTP_MAPPINGS[302], [('Content-Type', 'text/plain'), ('Location', exception.url)])
    return ['']


# Sample server

def run_itty(host='localhost', port=8080):
    """
    Runs the itty web server.
    
    Accepts an optional host (string) and port (integer) parameters.
    
    Uses Python's built-in wsgiref implementation. Easily replaced with other
    WSGI server implementations.
    """
    print 'itty starting up...'
    print 'Listening on http://%s:%s...' % (host, port)
    print 'Use Ctrl-C to quit.'
    print
    
    try:
        from wsgiref.simple_server import make_server
        srv = make_server(host, port, handle_request)
        srv.serve_forever()
    except KeyboardInterrupt:
        print "Shuting down..."
        import sys
        sys.exit()


if __name__ == '__main__':
    run_itty()
