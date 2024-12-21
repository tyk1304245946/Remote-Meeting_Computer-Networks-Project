import asyncio
from config import *


class ConferenceServer:
    def __init__(self, conference_id, conf_serve_port, data_serve_ports):
        self.conference_id = conference_id
        self.conf_serve_port = conf_serve_port
        self.data_serve_ports = data_serve_ports
        self.data_types = list(data_serve_ports.keys())
        self.clients_info = {}  # {client_addr: writer}
        self.client_conns = {}  # {data_type: {client_addr: writer}}
        self.running = True

    async def handle_data(self, reader, writer, data_type):
        addr = writer.get_extra_info('peername')
        port = writer.get_extra_info('sockname')[1]
        if data_type not in self.client_conns:
            self.client_conns[data_type] = {}
        self.client_conns[data_type][addr] = writer
        print(f'[Data] {data_type} connection from {addr} on port {port}')

        try:
            while self.running:
                data = await reader.read(1024*1024)
                if not data:
                    break
                # 转发数据给其他客户端
                for client_addr, client_writer in self.client_conns[data_type].items():
                    if client_addr != addr:
                        client_writer.write(data)
                        await client_writer.drain()
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

        # 启动数据服务器
        self.data_servers = []
        for data_type, port in self.data_serve_ports.items():
            server = await asyncio.start_server(
                lambda r, w, dt=data_type: self.handle_data(r, w, dt), SERVER_IP, port)
            self.data_servers.append(server)
            print(f'Data server for {data_type} started on port {port}')

        await self.conf_server.serve_forever()

    async def stop(self):
        self.running = False
        self.conf_server.close()
        await self.conf_server.wait_closed()
        for server in self.data_servers:
            server.close()
            await server.wait_closed()
        print('ConferenceServer stopped')


class MainServer:
    def __init__(self, server_ip, main_port):
        self.server_ip = server_ip
        self.server_port = main_port
        self.conference_servers = {}
        self.next_conference_id = 1

    async def handle_create_conference(self, _, writer):
        conference_id = self.next_conference_id
        self.next_conference_id += 1

        # 分配端口（简单实现，可以根据需要修改）
        conf_serve_port = MAIN_SERVER_PORT + conference_id * 10
        data_serve_ports = {
            'screen': conf_serve_port + 1,
            # 'camera': conf_serve_port + 2,
            # 'audio': conf_serve_port + 3,
        }

        # 创建并启动 ConferenceServer
        conference_server = ConferenceServer(conference_id, conf_serve_port, data_serve_ports)
        asyncio.create_task(conference_server.start())
        self.conference_servers[conference_id] = conference_server

        response = f'CREATE_OK {conference_id} {conf_serve_port} {data_serve_ports}\n'
        writer.write(response.encode())
        await writer.drain()
        print(f'Conference {conference_id} created')
        writer.close()
        await writer.wait_closed()

    async def handle_join_conference(self, _, writer, conference_id):
        if conference_id in self.conference_servers:
            conference_server = self.conference_servers[conference_id]
            response = f'JOIN_OK {conference_id} {conference_server.conf_serve_port} {conference_server.data_serve_ports}\n'
            writer.write(response.encode())
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
        if message == 'CREATE_CONFERENCE':
            await self.handle_create_conference(reader, writer)
        elif message.startswith('JOIN_CONFERENCE'):
            _, conf_id = message.split()
            await self.handle_join_conference(reader, writer, int(conf_id))
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