import asyncio
import json
import logging
import time
from concurrent.futures import TimeoutError as GetTimeoutError
import threading
import requests
from SignalR.Negotiator import Negotiator
from SignalR.Socket import Socket


class SignalRClient:
    """Documentation for SignalRClient

    """
    def __init__(self, url, hub, extra_params={}, is_safe=True):
        self.url = url
        self.hub = hub
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent':
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
        })
        self.negotiatior = Negotiator(url, hub, self.session, extra_params,
                                      is_safe)
        self._initialize_loop_and_queue()
        self._initialize_logger()
        self._set_controlling_booleans()
        self._invoked = 0
        self.messages = []
        self.extra_params = extra_params
        self.is_safe = is_safe
        self._buffered_messages = {}
        self._all_methods = {}

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

    def _set_controlling_booleans(self):
        self.can_listen = True
        self.can_initialize = False
        self.can_invoke = False
        self.break_flag = False

    def _add_socket_connection_to_loop(self):
        asyncio.ensure_future(self._create_socket_connection(), loop=self.loop)

    async def _create_socket_connection(self):
        async with Socket(self.url, self.hub, self.session,
                          self.negotiatior.data, self.loop, self.extra_params,
                          self.is_safe) as self.socket:
            self.logger.debug('<Socket Created>')
            await self._add_handlers_to_async_loop()
        self.logger.debug('<Connection Stopped>')
        self.loop.stop()

    async def _add_handlers_to_async_loop(self):
        handled_listener = self.handle_exception(self._listener())
        listener_task = asyncio.ensure_future(handled_listener, loop=self.loop)

        handled_initializer = self.handle_exception(self._initializer())
        initializer_task = asyncio.ensure_future(handled_initializer,
                                                 loop=self.loop)

        handled_invoker = self.handle_exception(self._invoker())
        invoker_task = asyncio.ensure_future(handled_invoker, loop=self.loop)

        handled_quitter = self.handle_exception(self._quitter())
        quitter_task = asyncio.ensure_future(handled_quitter, loop=self.loop)

        self.logger.debug('<All Handlers has been Created>')
        done, pending = await asyncio.wait(
            [listener_task, initializer_task, invoker_task, quitter_task],
            loop=self.loop,
            return_when=asyncio.FIRST_EXCEPTION)
        self.logger.debug('<Handlers tasks are done>')
        for task in pending:
            task.cancel()

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
            if self.can_listen:
                self.can_initialize = True
                try:
                    message = await asyncio.wait_for(
                        self.socket.websocket.recv(), 0.1)
                except GetTimeoutError:
                    message = ''
                if len(message) > 0:
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
                            # self.logger.debug(dict_data)
                            if dict_data['H'] == self.hub:
                                self.call_method(dict_data['M'],
                                                 dict_data['A'])
                        self.logger.debug('<End Message>')
                    else:
                        self.logger.debug('<Unknown Data>')
                        # self.logger.debug(data)
        self.logger.debug('<Listening Ended>')

    async def _initializer(self):
        while True:
            await asyncio.sleep(0)
            if self.can_initialize:
                self.initialize_conversation()
                self.can_invoke = True
                break
        self.logger.debug('<Initializing Ended>')

    async def _invoker(self):
        while True:
            await asyncio.sleep(0.05)
            if self.break_flag is True:
                break
            if self.can_invoke:
                # top = await self.invoke_queue.get()
                try:
                    top = await asyncio.wait_for(self.invoke_queue.get(), 0.1)
                except GetTimeoutError:
                    top = None

                if top is not None:
                    if 'break_flag' in top:
                        self.logger.info('Got Settings: {}'.format(top))
                        self.break_flag = top['break_flag']
                    else:
                        self.logger.info('Sending :{}'.format(top))
                        await self.socket.send(top)
                        self.logger.debug('<Sent>')
                        self.invoke_queue.task_done()
        self.logger.debug('<Invoking Ended>')

    async def _quitter(self):
        while True:
            await asyncio.sleep(0.2)
            if self.break_flag is True:
                break
            if self.can_quit():
                self.break_flag = True
        self.logger.debug('<Quitting Ended>')

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

    def can_quit(self):
        return False

    def initialize_conversation(self):
        if self.is_safe:
            url = 'https://' + self.url + '/start'
        else:
            url = 'http://' + self.url + '/start'
        client_protocol_version = 1.5
        params = {
            'transport': 'webSockets',
            'connectionToken': self.negotiatior.data['ConnectionToken'],
            'connectionData': json.dumps([{
                'name': self.hub
            }]),
            'clientProtocol': client_protocol_version,
        }
        params.update(self.extra_params)
        response = self.session.get(url, params=params)
        self.logger.debug('Conversation started with result of {}'.format(
            response.json()))

    def run(self):
        self.loop.run_forever()

    def add_connection_and_run(self):
        self._add_socket_connection_to_loop()
        self.run()

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
        self.thread = threading.Thread(target=self.add_connection_and_run)
        self.thread.daemon = True
        self.thread.start()

    def _stop(self):
        self._add_to_invoke_queue({'break_flag': True})
        self.thread.join()
