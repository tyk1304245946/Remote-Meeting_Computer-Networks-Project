import asyncio
import struct
from config import *
import asyncio
import socket

class RTPServer(asyncio.DatagramProtocol):
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.transport = None
        self.client_address = None
        self.client_conns = {}

    async def start_server(self):
        loop = asyncio.get_event_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self, local_addr=(self.host, self.port)
        )
        print(f"RTP Server started at {self.host}:{self.port}")

    def datagram_received(self, data, addr):
        # forward_host = addr[0]
        # forward_port = addr[1]
        # # print(f"Received data from {addr}, forwarding to {forward_host}:{forward_port}")
        # self.transport.sendto(data, (forward_host, forward_port))
        # # print(len(data))
        port = addr[1]
        print(f"Received data from {addr}:{port}")
        self.client_conns[addr] = self.transport
        for client_addr, transport in self.client_conns.items():
            print(f"Sending data to {client_addr}")
            transport.sendto(data, client_addr)

class RTPScreenServer(asyncio.DatagramProtocol):
    def __init__(self, host, port, conference_server):
        self.host = host
        self.port = port
        self.transport = None
        self.client_address = None
        self.client_conns = {}
        self.conference_server = conference_server

    async def start_server(self):
        loop = asyncio.get_event_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self, local_addr=(self.host, self.port)
        )
        print(f"RTP Server started at {self.host}:{self.port}")

    def datagram_received(self, data, addr):
        # forward_host = addr[0]
        # forward_port = addr[1]
        # # print(f"Received data from {addr}, forwarding to {forward_host}:{forward_port}")
        # self.transport.sendto(data, (forward_host, forward_port))
        # # print(len(data))
        port = addr[1]
        print(f"Received data from {addr}:{port}")
        self.client_conns[addr] = self.transport

        # print(self.client_conns)

        header = data[:12]
        payload = data[12:]

        user_info = payload[4:8].decode()
        # print(user_info)
    
        if self.conference_server.sharing_user is not None:
            # print(self.conference_server.sharing_user[4:])
            
            if user_info == self.conference_server.sharing_user[4:]:
                for client_addr, transport in self.client_conns.items():
                    print(f"Sending data to {client_addr}")
                    transport.sendto(data, client_addr)

class RTCPServer(asyncio.DatagramProtocol):
    def __init__(self, host, port, client_conns, user_list):
        self.host = host
        self.port = port
        self.client_conns = client_conns
        self.transport = None
        self.client_address = []
        self.user_list = user_list

    async def start_server(self):
        loop = asyncio.get_running_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self, local_addr=(self.host, self.port)
        )
        print(f"RTCP Server started at {self.host}:{self.port}")

        asyncio.create_task(self.send_message())

    async def send_message(self):
        while True:
            message = " ".join(self.user_list)
            for addr in self.client_address:
                self.transport.sendto(message.encode(), addr)
            await asyncio.sleep(2)

    def datagram_received(self, data, addr):
        self.client_address.append(addr)

        message = data.decode()
        print(f"Received RTCP message from {addr}: {message}")

class ConferenceServer:
    def __init__(self, conference_id, conf_serve_port, data_serve_ports):
        self.conference_id = conference_id
        self.conf_serve_port = conf_serve_port
        self.data_serve_ports = data_serve_ports
        self.data_types = list(data_serve_ports.keys())
        self.clients_info = {}  # {client_addr: writer}
        self.client_conns = {}  # {data_type: {client_addr: writer}}
        self.tasks = []
        self.running = True
        self.data = None
        self.sharing_user = None # (addr, port)
        self.user_list = []

    async def handle_data(self, reader, writer, data_type):
        addr = writer.get_extra_info('peername')
        port = writer.get_extra_info('sockname')[1]
        if data_type not in self.client_conns:
            self.client_conns[data_type] = {}
        self.client_conns[data_type][addr] = writer
        print(1)
        print(f'[Data] {data_type} connection from {addr} on port {port}')

        try:
            while self.running:
                data = bytearray()
                while True:
                    chunk = await reader.read(1024*1024)
                    # print(f'Received {len(chunk)} bytes')
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(chunk)<131072:
                        break
                self.data = data
                # print("len: ", len(data))

                if not data:
                    break
                # 转发数据给其他客户端
                for client_addr, client_writer in self.client_conns[data_type].items():
                    if client_addr != addr:
                        client_writer.write(data)
                        await client_writer.drain()
                        if data_type == 'text':
                            print(f'Sending text to {client_addr}: {data.decode()}')
                        # print(f'Sending {len(data)} bytes to {client_addr}')
        except ConnectionResetError:
            pass
        finally:
            print(f'[Data] {data_type} connection closed from {addr}')
            del self.client_conns[data_type][addr]
            writer.close()
            await writer.wait_closed()

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        self.clients_info[addr] = writer
        print(f'[Conference] Client connected: {addr}')

        try:
            while self.running:
                data = await reader.readline()
                if not data:
                    break
                message = data.decode().strip()
                print(f'Received from {addr}: {message}')
                # 处理会议中的请求（如退出等）
                if message == 'quit':
                    break
        except ConnectionResetError:
            pass
        finally:
            print(f'[Conference] Client disconnected: {addr}')
            del self.clients_info[addr]
            writer.close()
            await writer.wait_closed()

    async def start(self):
        # 启动会议控制服务器
        self.conf_server = await asyncio.start_server(self.handle_client, SERVER_IP, self.conf_serve_port)
        print(f'ConferenceServer started on port {self.conf_serve_port}')

        data_server = await asyncio.start_server(
                    lambda r, w: self.handle_data(r, w, 'text'),
                    SERVER_IP, self.data_serve_ports['text']
                )
        print(f'Text Data server started on port {self.data_serve_ports['text']}')

        # Create UDP sockets for data servers
        data_server_sockets = {}
        # self.data_servers = []
        for data_type, port in self.data_serve_ports.items():
            if data_type == 'text':
                pass
            elif data_type == 'screen':
                print(f'Starting RTP Screen server for {data_type} on port {port}')
                data_server = RTPScreenServer(SERVER_IP, port, self)
                data_server_sockets[data_type] = data_server.transport
                self.tasks.append(asyncio.create_task(data_server.start_server()))
                print(f'RTP Screen server for {data_type} started on port {port}')
            elif data_type == 'control':
                data_server = RTCPServer(SERVER_IP, port, self.client_conns, self.user_list)
                data_server_sockets[data_type] = data_server.transport
                self.tasks.append(asyncio.create_task(data_server.start_server()))
                print(f'RTCP server for {data_type} started on port {port}')
            else:
                print(f'Starting RTP Data server for {data_type} on port {port}')
                data_server = RTPServer(SERVER_IP, port)
                data_server_sockets[data_type] = data_server.transport
                self.tasks.append(asyncio.create_task(data_server.start_server()))
                print(f'RTP Data server for {data_type} started on port {port}')
        await asyncio.gather(*self.tasks)

    async def stop(self):
        self.running = False
        # for server in self.data_servers:
            # server.close()
            # await server.wait_closed()
        # self.conf_server.close()
        # await self.conf_server.wait_closed()
        print('ConferenceServer stopped')

    async def handle_cancel_conference(self, conference_id):
        print(f'Canceling conference {conference_id}')

        if conference_id == self.conference_id:
            items = list(self.client_conns['text'].items())  # 创建字典项的副本
            for addr, writer in items:
                # print("**********************")
                # print(addr)
                # print(writer)
                writer.write('CONFERENCE_CANCELED\n'.encode())
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            self.client_conns.clear()
            self.clients_info.clear()
            self.running = False
            print(f'Conference {conference_id} canceled')
        else:
            print(f'Conference {conference_id} not found')

    async def handle_share_conference(self, writer, user_name):
        if self.sharing_user is None:
            self.sharing_user = user_name
            print(f'Sharing user: {user_name}')
            writer.write('SHARE_OK\n'.encode())
            await writer.drain()
        elif self.sharing_user == user_name:
            self.sharing_user = None
            print(f'Sharing user: {self.sharing_user}')
            writer.write('SHARE_STOP\n'.encode())
            await writer.drain()
        else:
            print(f'Sharing user: {self.sharing_user}')
            writer.write('SHARE_BUSY\n'.encode())
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def add_user(self, user_name):
        self.user_list.append(user_name)
        print(f'User {user_name} added to conference {self.conference_id}\n', 'User list:', self.user_list)
    
    async def remove_user(self, user_name):
        self.user_list.remove(user_name)
        print(f'User {user_name} removed from conference {self.conference_id}\n', 'User list:', self.user_list)

class MainServer:
    def __init__(self, server_ip, main_port):
        self.server_ip = server_ip
        self.server_port = main_port
        self.conference_servers = {}
        self.next_conference_id = 1

    async def handle_create_conference(self, _, writer, user_name):
        conference_id = self.next_conference_id
        self.next_conference_id += 1

        # 分配端口（简单实现，可以根据需要修改）
        conf_serve_port = MAIN_SERVER_PORT + conference_id * 10
        data_serve_ports = {
            'screen': conf_serve_port + 1,
            # 'camera': conf_serve_port + 2,
            # 'audio': conf_serve_port + 3,
            'text': conf_serve_port + 4,
            'control': conf_serve_port + 5
        }

        # 创建并启动 ConferenceServer
        conference_server = ConferenceServer(conference_id, conf_serve_port, data_serve_ports)
        asyncio.create_task(conference_server.start())
        self.conference_servers[conference_id] = conference_server

        response = f'CREATE_OK {conference_id} {conf_serve_port} {data_serve_ports}\n'
        # add user to conference
        await conference_server.add_user(user_name)
        writer.write(response.encode())
        await writer.drain()
        print(f'Conference {conference_id} created')
        writer.close()
        await writer.wait_closed()

    async def handle_join_conference(self, _, writer, conference_id, user_name):
        print(f'Joining conference {conference_id}')
        if conference_id in self.conference_servers:
            conference_server = self.conference_servers[conference_id]
            response = f'JOIN_OK {conference_id} {conference_server.conf_serve_port} {conference_server.data_serve_ports}\n'
            await conference_server.add_user(user_name)
            writer.write(response.encode())
            await writer.drain()
        else:
            writer.write('ERROR Conference not found\n'.encode())
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def handle_cancel_conference(self, _, writer, conference_id):
        writer.write('CANCEL_OK\n'.encode())
        await writer.drain()
        if conference_id in self.conference_servers:
            conference_server = self.conference_servers[conference_id]
            self.conference_servers[conference_id] = None
            await conference_server.handle_cancel_conference(conference_id)
            response = 'CANCEL_OK\n'
            writer.write(response.encode())
            await writer.drain()
        else:
            response = 'ERROR Conference not found\n'
            writer.write(response.encode())
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def handle_get_conference_list(self, _, writer):
        response = 'CONFERENCE_LIST'
        print(self.conference_servers)
        for conference_id, conference_server in self.conference_servers.items():
            if conference_server is not None:
                response += f' {conference_id}'
        response += '\n'
        writer.write(response.encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def handle_share_conference(self, _, writer, conference_id, user_name):
        if conference_id in self.conference_servers:
            conference_server = self.conference_servers[conference_id]
            await conference_server.handle_share_conference(writer, user_name)
        else:
            writer.write('ERROR Conference not found\n'.encode())
            await writer.drain()
            writer.close()
            await writer.wait_closed()

    async def handle_quit_conference(self, _, writer, conference_id, user_name):
        print(f'Quitting conference {conference_id}')
        print (self.conference_servers)
        if conference_id in self.conference_servers:
            print(f'Quitting conference {conference_id}')
            conference_server = self.conference_servers[conference_id]
            await conference_server.remove_user(user_name)
            writer.write('QUIT_OK\n'.encode())
            await writer.drain()
        else:
            writer.write('ERROR Conference not found\n'.encode())
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def request_handler(self, reader, writer):
        data = await reader.readline()
        message = data.decode().strip()
        print(f'Received: {message}')
        if message.startswith('CREATE_CONFERENCE'):
            _, user_name = message.split()
            await self.handle_create_conference(reader, writer, user_name)
            # asyncio.create_task(self.handle_create_conference(reader, writer))
        elif message.startswith('JOIN_CONFERENCE'):
            _, conf_id, user_name = message.split()
            await self.handle_join_conference(reader, writer, int(conf_id), user_name)
        elif message.startswith('QUIT_CONFERENCE'):
            _, conf_id, user_name = message.split()
            await self.handle_quit_conference(reader, writer, int(conf_id), user_name)
        elif message.startswith('CANCEL_CONFERENCE'):
            _, conf_id = message.split()
            await self.handle_cancel_conference(reader, writer, int(conf_id))
        elif message == 'LIST_CONFERENCE':
            await self.handle_get_conference_list(reader, writer)
        elif message.startswith('SHARE_CONFERENCE'):
            _, conf_id, user_name = message.split()
            await self.handle_share_conference(reader, writer, int(conf_id), user_name)
        else:
            writer.write('ERROR Invalid command\n'.encode())
            await writer.drain()
            writer.close()
            await writer.wait_closed()

    def start(self):
        loop = asyncio.get_event_loop()
        coro = asyncio.start_server(self.request_handler, self.server_ip, self.server_port)
        server = loop.run_until_complete(coro)
        print(f'MainServer started on {self.server_ip}:{self.server_port}')
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        server.close()
        loop.run_until_complete(server.wait_closed())
        loop.run_until_complete(self.stop_all_conferences())
        loop.close()

    async def stop_all_conferences(self):
        for server in self.conference_servers.values():
            await server.stop()
        print('All conferences stopped')


if __name__ == '__main__':
    server = MainServer(SERVER_IP, MAIN_SERVER_PORT)
    server.start()
