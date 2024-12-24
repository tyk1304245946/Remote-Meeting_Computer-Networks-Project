import asyncio
import socket
import struct
import cv2
import numpy as np

def show_frame(payload):
    np_arr = np.frombuffer(payload, dtype=np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if frame is not None:
        cv2.imshow("Video", frame)
        cv2.waitKey(1)

async def rtp_client(host='127.0.0.1', port=5005):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(b'hello', (host, port))
    print(f"RTP client listening on {host}:{port}")

    while True:
        packet, _ = sock.recvfrom(65535)
        # RTP头12字节
        header = packet[:12]
        payload = packet[12:]

        # 解析RTP头
        rtp_header = struct.unpack('!BBHII', header)
        version = (rtp_header[0] >> 6) & 0x03
        pt = rtp_header[1] & 0x7F
        seq = rtp_header[2]
        timestamp = rtp_header[3]

        print(f"Recv RTP Packet: version={version}, payload_type={pt}, seq={seq}, timestamp={timestamp}, payload_size={len(payload)}")

        show_frame(payload)

async def main():
    client_task = asyncio.create_task(rtp_client())
    await client_task

if __name__ == '__main__':
    asyncio.run(main())