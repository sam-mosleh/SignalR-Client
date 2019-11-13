import asyncio
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .Connection import Connection
from .ConnectionData import ConnectionData
from .Negotiator import Negotiator
from .Socket import Socket


class SignalRHub:
    """Documentation for SignalRHub

    """

    def __init__(self, hub_name, message_handler, queue_adder,
                 calling_thread_pool):
        self._all_methods = {}
        self.hub_name = hub_name
        self.message_handler = message_handler
        self.queue_adder = queue_adder
        self.calling_thread_pool = calling_thread_pool
        self._initialize_logger()
        self.logger.setLevel(logging.WARNING)

    def _initialize_logger(self):
        self.logger = logging.getLogger('SignalRHub')
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            self.logger.addHandler(ch)
        self.logger.setLevel(logging.ERROR)

    def call_method(self, method_name, arguments):
        self.logger.info('Calling {}'.format(method_name))
        if method_name in self._all_methods:
            self.calling_thread_pool.submit(self._all_methods[method_name],
                                            *arguments)
        else:
            self.logger.warning(
                '{} method was not found in {}! you should set it...'.format(
                    method_name, self.hub_name))

    def on(self, method_name, function):
        self._all_methods[method_name] = function

    def invoke(self, method, *args):
        data_to_send, message_index = self.message_handler.create_invoke_message_from(
            self.hub_name, method, args)
        self.queue_adder(data_to_send)
        return self.post_invoke_waiting(message_index)

    def post_invoke_waiting(self, message_index):
        while not self.message_handler.is_message_ready(message_index):
            time.sleep(0.001)
        response = self.message_handler.get(message_index)
        if not response:
            self.logger.debug('<Empty Response>')
            return None
        return response


class MessageHandler:
    """Documentation for MessageHandler

    """

    def __init__(self):
        self._invoked = 0
        self._buffered_messages = {}

    def create_invoke_message_from(self, hub, method, args):
        message_index = self._invoked
        data_to_send = {'H': hub, 'M': method, 'A': args, 'I': message_index}
        self._buffered_messages[message_index] = None
        self._invoked += 1
        return data_to_send, message_index

    def is_message_ready(self, index):
        return self._buffered_messages[index] is not None

    def get(self, index):
        return self._buffered_messages.pop(index, None)

    def set(self, index, response):
        self._buffered_messages[index] = response


class SignalRClient:
    """Documentation for SignalRClient

    """

    def __init__(self,
                 url,
                 hub_names=[],
                 extra_params={},
                 is_safe=True,
                 thread_pool_size=32):
        self.url = url
        self.extra_params = extra_params
        self.is_safe = is_safe
        self.messages = []
        self.break_flag = False
        self.can_register_hub = True
        self.ready_state = False
        self.connection = Connection()
        self._initialize_loop_and_queue()
        self._initialize_logger()
        self.calling_thread_pool = ThreadPoolExecutor(thread_pool_size)
        self.message_handler = MessageHandler()
        self.hubs = {hub: self.create_hub(hub) for hub in hub_names}

    def get_hub(self, hub_name) -> SignalRHub:
        if hub_name in self.hubs:
            return self.hubs[hub_name]
        elif self.can_register_hub:
            self.hubs[hub_name] = self.create_hub(hub_name)
            return self.hubs[hub_name]
        else:
            self.logger.critical(
                'Cant register another hub after initializing')
            return None

    def create_hub(self, hub_name) -> SignalRHub:
        new_hub = SignalRHub(hub_name, self.message_handler,
                             self._add_to_invoke_queue,
                             self.calling_thread_pool)
        self.logger.debug('HUB {} created successfully'.format(hub_name))
        return new_hub

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
        self.logger.debug('<Negotiating Started>')
        self.can_register_hub = False
        self.connection_data = ConnectionData(self.url, self.hubs,
                                              self.extra_params, self.is_safe)
        self.negotiator = Negotiator(self.connection,
                                     self.connection_data).negotiate()
        self.logger.debug('<Negotiating Done>')
        self.connection_data.set_negotiating_data(self.negotiator.data)
        async with Socket(self.connection, self.connection_data,
                          self.loop) as self.socket:
            self.logger.debug('<Socket Connection Created>')
            self.initialize_conversation()
            await self._add_handlers_to_async_loop()
        self.logger.debug('<Socket Connection Stopped>')

    def initialize_conversation(self):
        url = self.connection_data.initialize_url
        params = self.connection_data.websocket_params
        response = self.connection.get(url, params=params)
        self.logger.debug('Conversation started with result of {}'.format(
            response.json()))

    async def _add_handlers_to_async_loop(self):
        listener_task = self.create_task_from(self._listener())
        invoker_task = self.create_task_from(self._invoker())
        self.ready_state = True
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
            self.logger.exception('Reason: {}'.format(error))
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
        data = json.loads(message)
        if 'I' in data:
            self.messages.append(data)
            self.logger.debug('Reponse={}'.format(data))
            if 'R' in data:
                self.message_handler.set(int(data['I']), data['R'])
            else:
                self.message_handler.set(int(data['I']), [])
        elif 'M' in data and data['M']:
            for dict_data in data['M']:
                if dict_data['H'] in self.hubs:
                    hub = self.hubs[dict_data['H']]
                    hub.call_method(dict_data['M'], dict_data['A'])
                else:
                    self.logger.warning('{} is not a registered hub'.format(
                        dict_data['H']))
        elif 'E' in data:
            self.logger.error(data['E'])
        elif data:
            self.logger.debug('<Unknown Data>')
            self.logger.debug(data)

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
                await self.process_invoke_message(top)
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

    def _add_to_invoke_queue(self, data):
        asyncio.Task(self.invoke_queue.put(data), loop=self.loop)

    def run(self):
        self.loop.run_until_complete(
            self._create_socket_and_start_conversation())

    def __enter__(self):
        self._start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._stop()

    def _start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()
        self.wait_until_ready()

    def wait_until_ready(self):
        while not self.ready_state:
            time.sleep(0.001)

    def _stop(self):
        self.logger.debug('<Breaking Loop>')
        self.break_loop()
        self.thread.join()
        self.logger.debug('<Joined>')

    def break_loop(self):
        self._add_to_invoke_queue({'break_flag': True})
