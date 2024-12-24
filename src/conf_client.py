import asyncio
from util import *
from random import randint
import string
from datetime import datetime
from config import *


class ConferenceClient:
    def __init__(self):
        # 初始化客户端
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
        self.username = USER_NAME+str(randint(0, 9999))
        self.text_reader = None
        self.text_writer = None


    async def create_conference(self):
        # 创建会议
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
            # await self.start_conference()
            # self.start_conference()
            asyncio.create_task(self.start_conference())

        else:
            print('Failed to create conference')
        #####################################
        writer.close()
        await writer.wait_closed()

    async def join_conference(self, conference_id):
        # 加入会议
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
            self.text_reader, self.text_writer = await asyncio.open_connection(SERVER_IP, self.data_serve_ports['text'])
            self.on_meeting = True
            print(f'Joined conference {self.conference_id}')
            # await self.start_conference()
            asyncio.create_task(self.start_conference())
        else:
            print('Failed to join conference')
        writer.close()
        await writer.wait_closed()

    async def quit_conference(self):
        # 退出会议
        self.on_meeting = False
        for task in self.recv_tasks + self.send_tasks:
            task.cancel()
        cv2.destroyAllWindows()  # 关闭所有 OpenCV 窗口
        self.recv_tasks.clear()
        self.send_tasks.clear()
        print('Quit conference')

    async def cancel_conference(self):
        # 取消会议
        if self.on_meeting:
            reader, writer = await asyncio.open_connection(*self.server_addr)
            writer.write(f'CANCEL_CONFERENCE {self.conference_id}\n'.encode())
            await writer.drain()
            # print('Waiting for response')###todo: 可能阻塞
            data = await reader.readline()
            message = data.decode().strip()
            print('Message: ', message)
            if message == 'CANCEL_OK':
                self.on_meeting = False
                for task in self.recv_tasks + self.send_tasks:
                    task.cancel()
                cv2.destroyAllWindows()  # 关闭所有 OpenCV 窗口
                self.recv_tasks.clear()
                self.send_tasks.clear()
                print('Conference canceled')
            else:
                print('Failed to cancel conference')
            writer.close()
            await asyncio.shield(writer.wait_closed())
        else:
            print('No conference to cancel')

    async def keep_share(self, data_type, port, capture_function, compress=None, fps=1):
        # 持续分享数据
        reader, writer = await asyncio.open_connection(SERVER_IP, port)
        
        print(f'keep_share Client writer is using port: {writer.get_extra_info("sockname")[1]}')
        try:
            while self.on_meeting:
                data = capture_function()
                # print(f'Sharing {data_type} on port {port}')
                # print(data)
                if compress:
                    data = compress(data)
                # print(f'Sending {len(data)} bytes')
                writer.write(data)
                await writer.drain()
                # await asyncio.sleep(5)
                await asyncio.sleep(1/fps)
        except asyncio.CancelledError:
            pass
        finally:
            print(f'Stop sharing {data_type} on port {port}')
            writer.close()
            await writer.wait_closed()

    ## todo: implement this function
    def share_switch(self, data_type):
        # 切换分享某种类型的数据（屏幕、摄像头、音频等）
        pass

    async def keep_recv(self, data_type, port, decompress=None):
        # 持续接收数据
        reader, writer = await asyncio.open_connection(SERVER_IP, port)
        print(f'keep_recv Client writer is using port: {writer.get_extra_info("sockname")[1]}')
        # writer = self.writer
        # reader = self.reader
        try:
            while self.on_meeting:
                # print(f'Receiving {data_type} on port {port}')
                data = bytearray()
                while True:
                    chunk = await reader.read(1024*1024)
                    # print(f'Received {len(chunk)} bytes')
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(chunk)<131072:
                        break
                # print(f'Received {len(data)} bytes')

                if len(data) == 20:
                    # quit when no data received
                    await self.quit_conference()

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
        # 输出数据
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
                cv2.imshow('Conference '+str(self.conference_id), cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR))
                cv2.waitKey(1)
            else:
                ## todo: 显示黑框
                pass

            # 播放接收到的音频
            if 'audio' in self.share_data:
                audio_data = self.share_data['audio']
                play_audio(audio_data)
            await asyncio.sleep(0.05)

            # if 'text' in self.share_data:
            #     print(self.share_data['text'])

    async def start_conference(self):
        # 启动会议
        # 启动数据接收和发送任务
        self.text_reader, self.text_writer = await asyncio.open_connection(SERVER_IP, self.data_serve_ports['text'])
        print(f'start_conference Client writer is using port: {self.text_writer.get_extra_info("sockname")[1]}')
        for data_type, port in self.data_serve_ports.items():
            if data_type in ['screen', 'camera']:
                # print(f'Start sharing {data_type} on port {port}')
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
            elif data_type == 'text':
                recv_task = asyncio.create_task(self.recv_text())
            self.send_tasks.append(send_task)
            self.recv_tasks.append(recv_task)

        # 启动输出任务
        output_task = asyncio.create_task(self.output_data())
        self.recv_tasks.append(output_task)

        tasks = self.recv_tasks + self.send_tasks
        # print('Tasks: ', tasks)
        await asyncio.gather(*tasks)
        # for task in tasks:
        #     print('Task: ', task)
        #     asyncio.run(task)

    async def list_conference(self):
        # 列出会议
        reader, writer = await asyncio.open_connection(*self.server_addr)
        writer.write('LIST_CONFERENCE\n'.encode())
        await writer.drain()
        data = await reader.readline()
        message = data.decode().strip()
        print('Message: ', message)
        if message.startswith('CONFERENCE_LIST'):
            conf_list = message.split(' ')
            if len(conf_list) == 1:
                print('No conference')
            else:
                # conf_list = eval(conf_list)
                conf_list = conf_list[1:]
                print('Conference List:')
                for conf in conf_list:
                    print("Conference", conf)
        else:
            print('Failed to list conference')
        writer.close()
        await writer.wait_closed()

    async def send_text(self, text):
        # 发送文本消息
        # print(self.data_serve_ports)
        # port = self.data_serve_ports['text']
        # reader, writer = await asyncio.open_connection(SERVER_IP, port)
        writer = self.text_writer
        writer.write(text.encode())
        print(f'text_me: {text}')
        # await writer.drain()
        # writer.close()
        # await writer.wait_closed()

    async def recv_text(self):
        # 接收文本消息
        # port = self.data_serve_ports['text']
        # reader, writer = await asyncio.open_connection(SERVER_IP, port)
        reader= self.text_reader
        while self.on_meeting:
            data = await reader.readline()
            message = data.decode().strip()
            if len(message) != 0:
                print("text: "+message)
            # writer.close()
            # await writer.wait_closed()
            await asyncio.sleep(1)

    async def start(self):
        # 启动客户端
        loop = asyncio.get_event_loop()
        print("Client started, your username is: ", self.username)
        while True:
            if not self.on_meeting:
                status = 'Free'
            else:
                status = f'OnMeeting-{self.conference_id}'

            recognized = True
            print(f'({status}) Please enter a operation (enter "?" to help): ')
            cmd_input = await loop.run_in_executor(None, input)
            cmd_input = cmd_input.strip().lower()
            # cmd_input = input(f'({status}) Please enter a operation (enter "?" to help): ')
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
                elif cmd_input == 'list':
                    await self.list_conference()
                else:
                    recognized = False
            elif len(fields) == 2 and fields[0] != 'text':
                if fields[0] == 'join':
                    input_conf_id = fields[1]
                    if input_conf_id.isdigit():
                        await self.join_conference(int(input_conf_id))
                    else:
                        print('[Warn]: Input conference ID must be in digital form')
                else:
                    recognized = False
            elif fields[0] == 'text':
                if len(fields) >= 2:
                    text = ''
                    for i in range(1, len(fields)):
                        text += ' ' + fields[i]
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    full_message = f'[{timestamp}] {self.username}: {text}\n'
                    # print(full_message)
                    await self.send_text(full_message)
                else:
                    recognized = False
                        
            else:
                recognized = False

            if not recognized:
                print(f'[Warn]: Unrecognized cmd_input {cmd_input}')


if __name__ == '__main__':
    client = ConferenceClient()
    asyncio.run(client.start())

#     async def start(self):
#         while True:
#             if not self.on_meeting:
#                 status = 'Free'
#             else:
#                 status = f'OnMeeting-{self.conference_id}'

#             recognized = True
#             cmd_input = input(f'({status}) Please enter a operation (enter "?" to help): ')
#             cmd_input = cmd_input.strip().lower()
#             fields = cmd_input.split(maxsplit=1)
#             if len(fields) == 1:
#                 if cmd_input in ('?', '？'):
#                     print(HELP)
#                 elif cmd_input == 'create':
#                     asyncio.create_task(self.create_conference())
#                 elif cmd_input == 'quit':
#                     asyncio.create_task(self.quit_conference())
#                 elif cmd_input == 'cancel':
#                     asyncio.create_task(self.cancel_conference())
#                 else:
#                     recognized = False
#             elif len(fields) == 2:
#                 if fields[0] == 'join':
#                     input_conf_id = fields[1]
#                     if input_conf_id.isdigit():
#                         asyncio.create_task(self.join_conference(int(input_conf_id)))
#                     else:
#                         print('[Warn]: Input conference ID must be in digital form')
#                 else:
#                     recognized = False
#             else:
#                 recognized = False

#             if not recognized:
#                 print(f'[Warn]: Unrecognized cmd_input {cmd_input}')

# # 修改主程序入口
# if __name__ == '__main__':
#     client = ConferenceClient()
#     asyncio.run(client.start())