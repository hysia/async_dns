'''
Async DNS server
'''
import asyncio
from .. import DNSMessage, UDP, InternetProtocol
from .. import resolver, logger, types
from ..cache import DNSMemCache

class DNSMixIn:
    '''DNS handler mix-in'''

    def __init__(self, resolver_, *k, **kw):
        super().__init__(*k, **kw)
        self.resolver = resolver_
        self.transport = None
        self.addr = None

    def send_data(self, data, addr):
        '''Send data to remote server.'''

        raise NotImplementedError

    async def handle(self, data, addr):
        '''Main handle method for protocols.'''

        msg = DNSMessage.parse(data)
        for question in msg.qd:
            res = await self.resolver.query(question.name, question.qtype)
            if res:
                res.qid = msg.qid
                data = res.pack()
                self.send_data(data, addr)
                len_data = len(data)
                # if len_data > 512:
                #     print(res)
                #     print(data)
                res_code = res.r
            else:
                len_data = 0
                res_code = -1
            logger.info(
                '[%s|%s|%s] %s %d %d', self.protocol, addr[0],
                types.get_name(question.qtype), question.name, res_code, len_data)
            break   # only one question is supported

class DNSDatagramProtocol(DNSMixIn, asyncio.DatagramProtocol):
    '''DNS server handler through UDP protocol.'''

    protocol = 'udp'

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        asyncio.ensure_future(self.handle(data, addr))

    def send_data(self, data, addr):
        self.transport.sendto(data, addr)

class DNSProtocol(DNSMixIn, asyncio.Protocol):
    '''DNS server handler through TCP protocol.'''

    protocol = 'tcp'

    def connection_made(self, transport):
        self.transport = transport
        self.addr = transport.get_extra_info('peername')

    def data_received(self, data):
        asyncio.ensure_future(self.handle(data, self.addr))

    def send_data(self, data, addr):
        self.transport.write(data)

async def start_server(
    host='', port=53, protocol_classes=(DNSProtocol, DNSDatagramProtocol),
    hosts=None, resolve_protocol=UDP, proxies=None):
    '''Start a DNS server.'''

    if not isinstance(resolve_protocol, InternetProtocol):
        resolve_protocol = InternetProtocol.get(resolve_protocol)
    tcp_protocol, udp_protocol = protocol_classes
    cache = DNSMemCache()
    cache.add_root_servers()
    proxy_resolver = resolver.ProxyResolver(resolve_protocol, cache)
    if hosts is not None:
        proxy_resolver.cache.parse_file(hosts)
    if proxies:
        proxy_resolver.set_proxies(proxies)
    loop = asyncio.get_event_loop()
    if tcp_protocol:
        server = await loop.create_server(
            lambda: tcp_protocol(proxy_resolver), host, port)
    else:
        server = None
    transport_arr = []
    if udp_protocol:
        if host:
            host_arr = [host] if isinstance(host, str) else host
        else:
            host_arr = ['0.0.0.0', '::']
        for host_bind in host_arr:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: udp_protocol(proxy_resolver),
                local_addr=(host_bind, port))
            transport_arr.append(transport)
    return server, transport_arr
