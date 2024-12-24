import asyncio
import math
import socket
import struct
from util import *
from config import *


class RTPClientProtocol(asyncio.DatagramProtocol):
    def __init__(self, host, port, conference_id, datatype, capture_function, compress=None, fps=10, decompress=None, share_data=None):
        self.host = host
        self.port = port
        self.transport = None
        self.datatype = datatype
        self.share_data = share_data
        self.capture_function = capture_function
        self.compress = compress
        self.decompress = decompress
        self.fps = fps
        self.frame_chunks = {}
        self.chunk_size = 50000
        self.frame_number = 0
        self.conference_id = conference_id


    async def start_client(self):
        loop = asyncio.get_event_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self, remote_addr=(self.host, self.port)
        )
        local_addr = self.transport.get_extra_info('sockname')
        print(f"RTP Client started at {local_addr[0]}:{local_addr[1]}")

        # asyncio.create_task(self.send_datagram())
        # asyncio.create_task(self.stream_video())
        # asyncio.create_task(self.stream_screen())
        # asyncio.create_task(self.output_data())

        self.tasks = [
            asyncio.create_task(self.stream_data()),
            asyncio.create_task(self.output_data())
        ]
        await asyncio.gather(*self.tasks)

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        # print(f"Received data from {addr}")
        # RTP头12字节
        header = data[:12]
        payload = data[12:]

        # Extract chunk information from the header (after RTP header)
        chunk_info = struct.unpack('!HH', payload[:4])  # First 4 bytes for chunk index and total chunks
        chunk_index, total_chunks = chunk_info

        # Remove the chunk info from payload
        payload_data = payload[4:]

        # Print RTP packet details
        print(f"Received RTP Packet: chunk_index={chunk_index}, total_chunks={total_chunks}, payload_size={len(payload_data)}")

        # Add the chunk to the dictionary
        if chunk_index not in self.frame_chunks:
            self.frame_chunks[chunk_index] = []

        self.frame_chunks[chunk_index].append(payload_data)

        # If we have received all chunks for a frame, reassemble and process the frame
        if len(self.frame_chunks) == total_chunks:
            # Reassemble all chunks into the full payload (frame)
            full_frame = b''.join(b''.join(self.frame_chunks[i]) for i in range(1, total_chunks + 1))
            print(f"Reassembled full frame of size {len(full_frame)} bytes")

            if self.decompress:
                full_frame = self.decompress(full_frame)
            self.share_data[self.datatype] = full_frame

            # Clear the frame chunks for the next frame
            self.frame_chunks.clear()

    async def send_rtp_packet(self, payload, chunk_index, total_chunks):
        """构建并发送 RTP 数据包，支持分块传输"""
        version = 2
        payload_type = 10 if self.datatype == 'audio' else 26
        sequence_number = self.frame_number
        timestamp = self.frame_number * 3000  # 时间戳示例
        ssrc = 12345  # 同步源 SSRC

        # 构建 RTP 数据包头
        rtp_header = struct.pack(
            '!BBHII',
            (version << 6) | payload_type,  # RTP 版本和有效负载类型
            0,  # 填充和扩展标志（此处为 0）
            sequence_number,  # 序列号
            timestamp,  # 时间戳
            ssrc  # SSRC
        )

        # 添加分块信息
        chunk_info = struct.pack('!HH', chunk_index, total_chunks)

        # 构建数据包，将 RTP 头、分块信息和数据有效载荷拼接
        rtp_packet = rtp_header + chunk_info + payload

        # 如果设置了客户端地址，则发送 RTP 数据包
        self.transport.sendto(rtp_packet)
        self.frame_number += 1

    async def stream_data(self):
        print(f"Start streaming {self.datatype} data")
        while True:
            payload = self.capture_function()
            if self.compress:
                payload = self.compress(payload)

            print(len(payload))

            # 如果 payload 超过了最大大小，进行分块传输
            if len(payload) > self.chunk_size:
                total_chunks = math.ceil(len(payload) / self.chunk_size)  # 计算总块数
                for i in range(total_chunks):
                    start = i * self.chunk_size
                    end = min(start + self.chunk_size, len(payload))
                    chunk = payload[start:end]
                    await self.send_rtp_packet(chunk,i + 1, total_chunks)
            else:
                # 如果有效负载较小，直接发送
                await self.send_rtp_packet(payload, 1, 1)
            await asyncio.sleep(1 / self.fps)

    async def output_data(self):
        # 输出数据
        while True:
            # print('Output data: ', self.share_data.keys())
            # 显示接收到的数据
            if 'screen' in self.share_data:
                screen_image = self.share_data['screen']
            else:
                screen_image = None
            if 'camera' in self.share_data:
                camera_images = [self.share_data['camera']]
            else:
                camera_images = None
            display_image = overlay_camera_images(screen_image, camera_images)
            if display_image:
                img_array = np.array(display_image)
                cv2.imshow('Conference '+str(self.conference_id), cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR))
                cv2.waitKey(1)
            else:
                ## todo: 显示黑框
                pass

            # 播放接收到的音频
            if 'audio' in self.share_data:
                audio_data = self.share_data['audio']
                play_audio(audio_data)
            await asyncio.sleep(1 / self.fps)

class ConferenceClient:
    def __init__(self):
        self.is_working = True
        self.server_addr = (SERVER_IP, MAIN_SERVER_PORT)
        self.on_meeting = False
        self.conference_id = None
        self.conf_serve_port = None
        self.data_serve_ports = {}
        # self.recv_tasks = []
        # self.send_tasks = []
        self.tasks = []
        self.data_server = []
        # 连接服务器
        # self.loop = asyncio.get_event_loop()
        self.received_chunks = {}
        self.share_data = {}

    async def create_conference(self):
        reader, writer = await asyncio.open_connection(*self.server_addr)
        writer.write('CREATE_CONFERENCE\n'.encode())
        await writer.drain()
        data = await reader.readline()
        message = data.decode().strip()
        if message.startswith('CREATE_OK'):
            _, conf_id, conf_port, data_ports = message.split(' ', 3)
            self.conference_id = int(conf_id)
            self.conf_serve_port = int(conf_port)
            self.data_serve_ports = eval(data_ports)
            self.on_meeting = True
            print(f'Conference {self.conference_id} created')
            await self.start_conference()
        else:
            print('Failed to create conference')
        writer.close()
        await writer.wait_closed()

    async def join_conference(self, conference_id):
        reader, writer = await asyncio.open_connection(*self.server_addr)
        writer.write(f'JOIN_CONFERENCE {conference_id}\n'.encode())
        await writer.drain()
        data = await reader.readline()
        message = data.decode().strip()
        if message.startswith('JOIN_OK'):
            _, conf_id, conf_port, data_ports = message.split(' ', 3)
            self.conference_id = int(conf_id)
            self.conf_serve_port = int(conf_port)
            self.data_serve_ports = eval(data_ports)
            self.on_meeting = True
            print(f'Joined conference {self.conference_id}')
            await self.start_conference()
        else:
            print('Failed to join conference')
        writer.close()
        await writer.wait_closed()

    async def quit_conference(self):
        self.on_meeting = False
        for task in self.recv_tasks + self.send_tasks:
            task.cancel()
        print('Quit conference')

    async def cancel_conference(self):
        if self.on_meeting:
            self.on_meeting = False
            # todo: cancle the conference on server side
            for task in self.recv_tasks + self.send_tasks:
                task.cancel()
            print('Conference canceled')
        else:
            print('No conference to cancel')

    ## todo: implement this function
    def share_switch(self, data_type):
        '''
        switch for sharing certain type of data (screen, camera, audio, etc.)
        '''
        pass

    async def start_conference(self):
        # 启动数据接收和发送任务
        for data_type, port in self.data_serve_ports.items():
            print(f'Start sharing {data_type} on port {port}')
            if data_type == 'screen':
                data_server = RTPClientProtocol(SERVER_IP, port, self.conference_id,
                                                data_type, fps=15,
                                                capture_function=capture_screen,
                                                compress=compress_screen,
                                                decompress=decompress_screen,
                                                share_data=self.share_data)
            elif data_type == 'camera':
                data_server = RTPClientProtocol(SERVER_IP, port, self.conference_id,
                                                data_type, fps=15,
                                                capture_function=capture_camera,
                                                compress=compress_screen,
                                                decompress=decompress_screen,
                                                share_data=self.share_data)

            elif data_type == 'audio':
                data_server = RTPClientProtocol(SERVER_IP, port, self.conference_id,
                                                data_type, fps=50,
                                                capture_function=capture_voice,
                                                share_data=self.share_data)
            self.tasks.append(asyncio.create_task(data_server.start_client()))
            self.data_server.append(data_server)

        await asyncio.gather(*self.tasks)

    async def start(self):
        while True:
            if not self.on_meeting:
                status = 'Free'
            else:
                status = f'OnMeeting-{self.conference_id}'

            recognized = True
            cmd_input = input(f'({status}) Please enter a operation (enter "?" to help): ').strip().lower()
            fields = cmd_input.split(maxsplit=1)
            if len(fields) == 1:
                if cmd_input in ('?', '？'):
                    print(HELP)
                elif cmd_input == 'create':
                    await self.create_conference()
                elif cmd_input == 'quit':
                    await self.quit_conference()
                elif cmd_input == 'cancel':
                    await self.cancel_conference()
                else:
                    recognized = False
            elif len(fields) == 2:
                if fields[0] == 'join':
                    input_conf_id = fields[1]
                    if input_conf_id.isdigit():
                        await self.join_conference(int(input_conf_id))
                    else:
                        print('[Warn]: Input conference ID must be in digital form')
                else:
                    recognized = False
            else:
                recognized = False

            if not recognized:
                print(f'[Warn]: Unrecognized cmd_input {cmd_input}')


if __name__ == '__main__':
    client = ConferenceClient()
    asyncio.run(client.start())