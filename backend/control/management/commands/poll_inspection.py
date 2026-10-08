import time,uuid
from django.core.management.base import BaseCommand
from control.worker import round_poll
class Command(BaseCommand):
    help='Bounded single-owner GET-only inspection polling'
    def add_arguments(self,p):p.add_argument('--once',action='store_true')
    def handle(self,*args,**opts):
        owner=str(uuid.uuid4())
        while True:
            start=time.monotonic();self.stdout.write(str(round_poll(owner)))
            if opts['once']:return
            time.sleep(max(0,20-(time.monotonic()-start)))
