import asyncio
import socket
import struct
import cv2
import numpy as np
import math

class RTPServer(asyncio.DatagramProtocol):
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.transport = None
        self.client_address = None
        self.chunk_size = 1500
        self.frame_number = 0

    async def start_server(self):
        loop = asyncio.get_event_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self, local_addr=(self.host, self.port)
        )
        print(f"RTP Server started at {self.host}:{self.port}")

    def datagram_received(self, data, addr):
        print(f"Received connection from {addr}")
        self.client_address = addr


    async def send_rtp_packet(self, payload, chunk_index, total_chunks):
        """构建并发送 RTP 数据包，支持分块传输"""
        version = 2
        payload_type = 26  # JPEG
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
            ssrc)  # SSRC

        # 添加分块信息
        chunk_info = struct.pack('!HH', chunk_index, total_chunks)

        # 构建数据包，将 RTP 头、分块信息和数据有效载荷拼接
        rtp_packet = rtp_header + chunk_info + payload

        # 如果设置了客户端地址，则发送 RTP 数据包
        if self.client_address:
            self.transport.sendto(rtp_packet, self.client_address)
    
        self.frame_number += 1
    

    async def stream_video(self, video_path):
        cap = cv2.VideoCapture(video_path)
        frame_number = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Encode the frame as JPEG
            _, encoded_frame = cv2.imencode('.jpg', frame)
            payload = encoded_frame.tobytes()

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

            # 模拟 30 FPS 发送
            await asyncio.sleep(1 / 30)

        cap.release()
    

async def main():
    server = RTPServer('127.0.0.1', 5005)
    await server.start_server()
    # await server.stream_video('14849779612_CPXUgtMMEMHFtKAK.mp4')
    await server.stream_video(0)

if __name__ == '__main__':
    asyncio.run(main())
