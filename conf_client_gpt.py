import asyncio
from util import *
from config import *


class ConferenceClient:
    def __init__(self):
        self.is_working = True
        self.server_addr = (SERVER_IP, MAIN_SERVER_PORT)
        self.on_meeting = False
        self.conference_id = None
        self.conf_serve_port = None
        self.data_serve_ports = {}
        self.share_data = {}
        self.recv_tasks = []
        self.send_tasks = []
        # 连接服务器
        self.loop = asyncio.get_event_loop()


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

    async def keep_share(self, data_type, port, capture_function, compress=None, fps=30):
        reader, writer = await asyncio.open_connection(SERVER_IP, port)
        try:
            while self.on_meeting:
                data = capture_function()
                if compress:
                    data = compress(data)
                writer.write(data)
                await writer.drain()
                await asyncio.sleep(1 / fps)
        except asyncio.CancelledError:
            pass
        finally:
            print(f'Stop sharing {data_type} on port {port}')
            writer.close()
            await writer.wait_closed()

    async def keep_recv(self, data_type, port, decompress=None):
        reader, writer = await asyncio.open_connection(SERVER_IP, port)
        try:
            while self.on_meeting:
                # print(f'Receiving {data_type} on port {port}')
                data = bytearray()
                while True:
                    chunk = await reader.read(4096)
                    if not chunk:
                        break
                    data.extend(chunk)
                if decompress:
                    data = decompress(data)
                self.share_data[data_type] = data
        except asyncio.CancelledError:
            pass
        finally:
            print(f'Stop receiving {data_type} on port {port}')
            writer.close()
            await writer.wait_closed()

    async def output_data(self):
        while self.on_meeting:
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
                cv2.imshow('Conference', cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR))
                cv2.waitKey(1)

            # 播放接收到的音频
            if 'audio' in self.share_data:
                audio_data = self.share_data['audio']
                play_audio(audio_data)
            await asyncio.sleep(0.05)       

    async def start_conference(self):
        # 启动数据接收和发送任务
        for data_type, port in self.data_serve_ports.items():
            if data_type in ['screen', 'camera']:
                print(f'Start sharing {data_type} on port {port}')
                send_task = asyncio.create_task(self.keep_share( 
                    data_type, port,
                    capture_function=capture_screen if data_type == 'screen' else capture_camera,
                    compress=compress_image))
                recv_task = asyncio.create_task(self.keep_recv(
                    data_type, port, decompress=decompress_image))
            elif data_type == 'audio':
                send_task = asyncio.create_task(self.keep_share(
                    data_type, port, capture_function=capture_voice))
                recv_task = asyncio.create_task(self.keep_recv(
                    data_type, port))
            self.send_tasks.append(send_task)
            self.recv_tasks.append(recv_task)

        # 启动输出任务
        output_task = asyncio.create_task(self.output_data())
        self.recv_tasks.append(output_task)

        tasks = self.recv_tasks + self.send_tasks
        await asyncio.gather(*tasks)


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