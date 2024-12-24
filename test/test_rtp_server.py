import asyncio
import socket
import struct
import cv2

class RTPServer(asyncio.DatagramProtocol):
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.transport = None
        self.client_address = None

    async def start_server(self):
        loop = asyncio.get_event_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self, local_addr=(self.host, self.port)
        )
        print(f"RTP Server started at {self.host}:{self.port}")

    def datagram_received(self, data, addr):
        print(f"Received connection from {addr}")
        self.client_address = addr

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

            # Build RTP packet header
            version = 2
            payload_type = 26  # JPEG
            sequence_number = frame_number
            timestamp = frame_number * 3000  # Example timestamp increment
            ssrc = 12345

            rtp_header = struct.pack('!BBHII', 
                                     (version << 6) | payload_type,
                                     0,
                                     sequence_number,
                                     timestamp,
                                     ssrc)
            
            rtp_packet = rtp_header + payload

            # Send RTP packet
            if self.client_address:
                self.transport.sendto(rtp_packet, self.client_address)

            frame_number += 1
            await asyncio.sleep(1 / 30)  # Simulate 30 FPS

        cap.release()
    

async def main():
    server = RTPServer('127.0.0.1', 5005)
    await server.start_server()
    # await server.stream_video('14849779612_CPXUgtMMEMHFtKAK.mp4')
    await server.stream_video(0)

if __name__ == '__main__':
    asyncio.run(main())
