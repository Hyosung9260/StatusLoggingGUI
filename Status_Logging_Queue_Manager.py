import queue

q_dict = {'APP_RUN0': queue.Queue(),
          'APP_RUN1': queue.Queue(),
          'APP_RUN2': queue.Queue()}


def clear_queue(qq):
    for key, val in qq.items():
        while not val.empty():
            val.get()
    print('[Message] All queues are cleared')