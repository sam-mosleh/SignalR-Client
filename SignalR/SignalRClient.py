import asyncio
import json
import logging
import threading
import time

import requests

from SignalR.Negotiator import Negotiator
from SignalR.Socket import Socket


class SignalRClient:
    """Documentation for SignalRClient

    """

    def __init__(self, url, hub, extra_params={}, is_safe=True):
        self.url = url
        self.hub = hub
        self.extra_params = extra_params
        self.is_safe = is_safe
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent':
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
        })
        self._initialize_loop_and_queue()
        self._initialize_logger()
        self._invoked = 0
        self.messages = []
        self._buffered_messages = {}
        self._all_methods = {}
        self.break_flag = False
        self.negotiator = Negotiator(self.url, self.hub, self.session,
                                     self.extra_params, self.is_safe)

    def _initialize_loop_and_queue(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.invoke_queue = asyncio.Queue(loop=self.loop)

    def _initialize_logger(self):
        self.logger = logging.getLogger('SignalRClient')
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            self.logger.addHandler(ch)
        self.logger.setLevel(logging.ERROR)

    async def _create_socket_and_start_conversation(self):
        async with Socket(self.url, self.hub, self.session,
                          self.negotiator.data, self.loop, self.extra_params,
                          self.is_safe) as self.socket:
            self.logger.debug('<Socket Created>')
            self.initialize_conversation()
            await self._add_handlers_to_async_loop()
        self.logger.debug('<Connection Stopped>')

    async def _add_handlers_to_async_loop(self):
        listener_task = self.create_task_from(self._listener())
        invoker_task = self.create_task_from(self._invoker())
        self.logger.debug('<All Handlers has been Created>')
        done, pending = await asyncio.wait([listener_task, invoker_task],
                                           loop=self.loop,
                                           return_when=asyncio.FIRST_EXCEPTION)
        self.logger.debug('<Handlers tasks are done>')
        for task in pending:
            task.cancel()

    def create_task_from(self, coroutine):
        handled_coroutine = self.handle_exception(coroutine)
        return asyncio.ensure_future(handled_coroutine, loop=self.loop)

    async def handle_exception(self, coroutine):
        try:
            await coroutine
        except Exception as error:
            self.logger.exception('Exception occurred.')
            self.logger.error('Reason: {}'.format(error))
            self.loop.stop()

    async def _listener(self):
        while True:
            await asyncio.sleep(0)
            if self.break_flag is True:
                break
            try:
                message = await asyncio.wait_for(self.socket.websocket.recv(),
                                                 0.01)
            except asyncio.TimeoutError:
                message = None
            if message:
                self.process_message(message)
        self.logger.debug('<Listening Ended>')

    def process_message(self, message):
        # self.logger.debug('Im {} Listening'.format(self))
        data = json.loads(message)
        if 'R' in data:
            self.messages.append(data)
            self.logger.debug('<Response>')
            self.logger.info(data)
            self.logger.debug('<End Response>')
            self._buffered_messages[int(data['I'])] = data['R']
        elif 'M' in data and data['M']:
            self.logger.debug('<Message>')
            for dict_data in data['M']:
                if dict_data['H'] == self.hub:
                    self.call_method(dict_data['M'], dict_data['A'])
                else:
                    self.logger.warning(dict_data)
                self.logger.debug('<End Message>')
        else:
            self.logger.debug('<Unknown Data>')
            # self.logger.debug(data)

    async def _invoker(self):
        while True:
            await asyncio.sleep(0)
            if self.break_flag is True:
                break
            # This accelerates top = await self.invoke_queue.get()
            try:
                top = await asyncio.wait_for(self.invoke_queue.get(), 0.01)
            except asyncio.TimeoutError:
                top = None
            if top:
                self.process_invoke_message(top)
        self.logger.debug('<Invoking Ended>')

    async def process_invoke_message(self, message):
        if 'break_flag' in message:
            self.logger.info('Got Settings: {}'.format(message))
            self.break_flag = message['break_flag']
        else:
            self.logger.info('Sending :{}'.format(message))
            await self.socket.send(message)
            self.logger.debug('<Sent>')
            self.invoke_queue.task_done()

    def invoke(self, method, data=[]):
        # self.generate_message()
        message_index = self._invoked
        data_to_send = {
            'H': self.hub,
            'M': method,
            'A': data,
            'I': message_index
        }
        self._buffered_messages[message_index] = []
        self._add_to_invoke_queue(data_to_send)
        self._invoked += 1
        return self.post_invoke_waiting(message_index)

    def _add_to_invoke_queue(self, data):
        asyncio.Task(self.invoke_queue.put(data), loop=self.loop)

    def post_invoke_waiting(self, message_index):
        while not self._buffered_messages[message_index]:
            time.sleep(0.001)
        return self._buffered_messages.pop(message_index, None)

    def initialize_conversation(self):
        url = SignalRClient.get_initialize_url(self.url, self.is_safe)
        params = SignalRClient.make_initialize_conversation_params(
            self.hub, self.negotiator, self.extra_params)
        response = self.session.get(url, params=params)
        self.logger.debug('Conversation started with result of {}'.format(
            response.json()))

    @staticmethod
    def get_initialize_url(url, is_safe):
        if is_safe:
            return 'https://' + url + '/start'
        else:
            return 'http://' + url + '/start'

    @staticmethod
    def make_initialize_conversation_params(hub_name,
                                            negotiator,
                                            extra_params={},
                                            client_protocol_version=1.5):
        params = {
            'transport': 'webSockets',
            'connectionToken': negotiator.data['ConnectionToken'],
            'connectionData': json.dumps([{
                'name': hub_name
            }]),
            'clientProtocol': client_protocol_version,
        }
        params.update(extra_params)
        return params

    def run(self):
        self.loop.run_until_complete(
            self._create_socket_and_start_conversation())

    def call_method(self, method_name, arguments):
        if method_name in self._all_methods:
            self._all_methods[method_name](arguments)
        else:
            self.logger.warning(
                '{} method was not found! you should set it...'.format(
                    method_name))

    def on(self, method_name, function):
        self._all_methods[method_name] = function

    def __enter__(self):
        self._start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._stop()

    def _start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()

    def _stop(self):
        self.logger.debug('<Breaking Loop>')
        self.break_loop()
        self.thread.join()
        self.logger.debug('<Joined>')

    def break_loop(self):
        self._add_to_invoke_queue({'break_flag': True})
