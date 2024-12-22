import asyncio
import aiosip
import aiortsp
from util import *

# ConferenceServer 需要设置为RTP服务器，就是还没搞懂clients_info和client_conns是干啥的
class ConferenceServer:
    def __init__(self, ):
        # async server
        self.conference_id = None  # conference_id for distinguish difference conference
        self.conf_serve_ports = None
        self.data_serve_ports = {}
        self.data_types = ['screen', 'camera', 'audio']  # example data types in a video conference
        self.clients_info = None
        self.client_conns = None
        self.mode = 'Client-Server'  # or 'P2P' if you want to support peer-to-peer conference mode

    async def handle_data(self, reader, writer, data_type):
        """
        running task: receive sharing stream data from a client and decide how to forward them to the rest clients
        """

    async def handle_client(self, reader, writer):
        """
        running task: handle the in-meeting requests or messages from clients
        """

    async def log(self):
        while self.running:
            print('Something about server status')
            await asyncio.sleep(LOG_INTERVAL)

    async def cancel_conference(self):
        """
        handle cancel conference request: disconnect all connections to cancel the conference
        """

    def start(self):
        '''
        start the ConferenceServer and necessary running tasks to handle clients in this conference
        '''


class MainServer:
    def __init__(self, server_ip, main_port):
        self.server_ip = server_ip
        self.server_port = main_port
        self.conference_servers = {}  # conference_id -> ConferenceServer
        self.app = aiosip.Application()

    async def handle_create_conference(self, request, message):
        """
        create conference: create and start the corresponding ConferenceServer, and reply necessary info to client
        """
        conference_id = len(self.conference_servers) + 1
        # Create a new conference server
        port = 5000 + len(self.conference_servers)  # Assign a unique port for the conference
        conf_server = ConferenceServer(conference_id, self.server_ip, port)
        self.conference_servers[conference_id] = conf_server
        asyncio.create_task(conf_server.start())

        conf_server = self.conference_servers[conference_id]

        # Respond with conference details (host and port)
        response = aiosip.Response.from_request(request, status_code=200, reason="OK")
        response.headers['RTP-Host'] = self.server_ip
        response.headers['RTP-Port'] = str(conf_server.port)
        await request.send_response(response)
        print(f"[MainServer] Successfully created conference {conference_id}.")

    async def handle_join_conference(self, request, message):
        """
        join conference: search corresponding conference_info and ConferenceServer, and reply necessary info to client
        """
        conference_id = message.headers.get('Conference-ID', None)
        if conference_id not in self.conference_servers:
            response = aiosip.Response.from_request(request, status_code=404, reason=f"Conference {conference_id} not found")
            await request.send_response(response)
            print(f"[MainServer] Error: conference {conference_id} not found when handling JOIN request.")
        else:
            conf_server = self.conference_servers[conference_id]
            response = aiosip.Response.from_request(request, status_code=200, reason="OK")
            response.headers['RTP-Host'] = self.server_ip
            response.headers['RTP-Port'] = str(conf_server.port)
            await request.send_response(response)
            print(f"[MainServer] JOIN {conference_id} handled.")

    async def handle_quit_conference(self, request, message):
        """
        quit conference (in-meeting request & or no need to request)
        """
        conference_id = message.headers.get('Conference-ID', None)
        if conference_id in self.conference_servers:
            conference_server = self.conference_servers[conference_id]
            if len(conference_server.clients) == 1:
                # Close the conference server if there is no client in the conference
                del self.conference_servers[conference_id]
                response = aiosip.Response.from_request(request, status_code=200, reason="OK")
                await request.send_response(response)
                print(f"[MainServer] Quit {conference_id} handled and conference is canceled.")
            else:
# -------------------------------------------这里还没写完-------------------------------------------------





                
                response = aiosip.Response.from_request(request, status_code=200, reason="OK")
                await request.send_response(response)
                print(f"[MainServer] Quit {conference_id} handled.")
        else:
            response = aiosip.Response.from_request(request, status_code=404, reason=f"Conference {conference_id} not found")
            await request.send_response(response)
            print(f"[MainServer] Error: conference {conference_id} not found when handling QUIT request.")

    async def handle_cancel_conference(self, request, message):
        """
        cancel conference (in-meeting request, a ConferenceServer should be closed by the MainServer)
        """
        conference_id = message.headers.get('Conference-ID', None)
        del self.conference_servers[conference_id]
        response = aiosip.Response.from_request(request, status_code=200, reason="OK")
        await request.send_response(response)
        print(f"[MainServer] Conference {conference_id} is canceled.")

    async def request_handler(self, protocol, message):
        """
        running task: handle out-meeting (or also in-meeting) requests from clients
        """
        if message.method == 'CREATE':
            await self.handle_create_conference(protocol, message)
        elif message.method == 'QUIT':
            await self.handle_quit_conference(protocol, message)
        elif message.method == 'JOIN':
            await self.handle_join_conference(protocol, message)
        elif message.method == 'CANCEL':
            await self.handle_cancel_conference(protocol, message)
        else:
            response = aiosip.Response.from_request(protocol, status_code=501, reason="Not Implemented")
            await protocol.send_response(response)

    async def start(self):
        """
        Start the SIP server to handle requests.
        """
        print(f"[MainServer] Starting SIP server on {self.server_ip}:{self.server_port}")
        await self.app.listen(self.server_ip, self.server_port, self.request_handler)

    def run(self):
        """
        Run the main server.
        """
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.start())
            loop.run_forever()
        except KeyboardInterrupt:
            print("[MainServer] Shutting down...")
        finally:
            loop.run_until_complete(self.app.close())
            loop.close()


if __name__ == '__main__':
    server = MainServer(SERVER_IP, MAIN_SERVER_PORT)
    server.run()
