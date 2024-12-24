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

    # Dictionary to store chunks for each frame
    frame_chunks = {}

    while True:
        # Receive RTP packet (max 65535 bytes)
        packet, _ = sock.recvfrom(65535)

        # Extract the RTP header (first 12 bytes)
        header = packet[:12]
        payload = packet[12:]

        # Extract chunk information from the header (after RTP header)
        chunk_info = struct.unpack('!HH', payload[:4])  # First 4 bytes for chunk index and total chunks
        chunk_index, total_chunks = chunk_info

        # Remove the chunk info from payload
        payload_data = payload[4:]

        # Print RTP packet details
        print(f"Received RTP Packet: chunk_index={chunk_index}, total_chunks={total_chunks}, payload_size={len(payload_data)}")

        # Add the chunk to the dictionary
        if chunk_index not in frame_chunks:
            frame_chunks[chunk_index] = []

        frame_chunks[chunk_index].append(payload_data)

        # If we have received all chunks for a frame, reassemble and process the frame
        if len(frame_chunks) == total_chunks:
            # Reassemble all chunks into the full payload (frame)
            full_frame = b''.join(b''.join(frame_chunks[i]) for i in range(1, total_chunks + 1))
            print(f"Reassembled full frame of size {len(full_frame)} bytes")

            # Display the frame (or process it further)
            show_frame(full_frame)

            # Clear the frame chunks for the next frame
            frame_chunks.clear()


async def main():
    client_task = asyncio.create_task(rtp_client())
    await client_task

if __name__ == '__main__':
    asyncio.run(main())