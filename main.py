# Copyright (c) 2020 Alex Carrega <contact@alexcarrega.com>
# author: Alex Carrega <contact@alexcarrega.com>

import json
import threading
from datetime import datetime
from string import Template
from subprocess import PIPE, CompletedProcess, run
from typing import Dict, Iterable, List, TypeVar

from bs4 import BeautifulSoup
from dynaconf import Dynaconf
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts.prompt import PromptSession
from prompt_toolkit.validation import ValidationError, Validator
from pygments import formatters, highlight, lexers

T_Data = TypeVar('T_Data', bound='Data')

NOT_AVAILABLE = 'N.A.'


def get_keys(data: Iterable[str]) -> List[str]:
    return list(map(lambda item: item.strip().lower(), data))


class Data:
    def __init__(self: T_Data):
        self.update()
        self.last_exec_start = NOT_AVAILABLE
        self.last_exec_end = datetime.now()
        self.last_exec_ret_code = NOT_AVAILABLE

    def update(self: T_Data) -> None:
        self.settings = Dynaconf(settings_files=["settings.yaml", ".secrets.yaml"])
        self.available_commands = get_keys(self.settings.get('commands', {}).keys()) + ['q']
        t = threading.Timer(1, self.update)
        t.daemon = True
        t.start()


T_CommandValidator = TypeVar('T_CommandValidator', bound='CommandValidator')


class CommandValidator(Validator):
    def __init__(self: T_CommandValidator, data: Data):
        self.data = data

    def validate(self: T_CommandValidator, document: Document) -> None:
        text = document.text.strip().lower()
        if text not in self.data.available_commands:
            raise ValidationError(message=f'Command {text} not found')


def exec(command: str, data: Data) -> CompletedProcess[str]:
    data.last_exec_start = datetime.now()
    command = Template(command).substitute(**data.settings.get('vars', {}))
    output = run(f'{command}', check=False, shell=True,
                 stdout=PIPE, stderr=PIPE, universal_newlines=True)
    data.last_exec_end = datetime.now()
    data.last_exec_ret_code = output.returncode
    return output


def format(data: str, type: str, lines: bool) -> str:
    if type == 'html':
        output = BeautifulSoup(data, features='html5lib').prettify()
        output = highlight(output, lexers.HtmlLexer(), formatters.TerminalFormatter())
    if type == 'json':
        json_data = json.loads(data)
        output = json.dumps(json_data, indent=4, sort_keys=True)
        output = highlight(output, lexers.JsonLexer(), formatters.TerminalFormatter())
    if type == 'std':
        output = data
    if lines:
        return '\n'.join(map(lambda line: '{0:>5}'.format(line[0]) + '.\t' + line[1], enumerate(output.split('\n'))))
    else:
        return output


def bottom_toolbar(data):
    ret_code_style = 'red' if data.last_exec_ret_code == NOT_AVAILABLE or data.last_exec_ret_code > 0 else 'green'
    if data.last_exec_start == NOT_AVAILABLE:
        duration = NOT_AVAILABLE
    else:
        duration = (data.last_exec_end - data.last_exec_start).total_seconds()
    return lambda: HTML(f'<aaa fg="blue" bg="white"> Time: <b>{data.last_exec_end}</b> </aaa> - <aaa fg="lightyellow"> Duration: <b>{duration}</b> </aaa> - <aaa fg="dark{ret_code_style}" bg="white"> Return code: <b>{data.last_exec_ret_code}</b> </aaa>')


def main():
    data = Data()
    session = PromptSession(history=FileHistory('.prompt-able'))

    while True:
        input = session.prompt(f'{data.settings.prompt} ',
                               bottom_toolbar=bottom_toolbar(data),
                               auto_suggest=AutoSuggestFromHistory(),
                               completer=WordCompleter(data.available_commands),
                               validator=CommandValidator(data),
                               validate_while_typing=False).strip().lower()
        if input in data.settings.commands.keys():
            command_input = data.settings.commands.get(input)
            type = command_input.output.strip().lower()
            lines = command_input.lines
            output_process = exec(command_input.exec, data)
            output_stdout = format(output_process.stdout, type, lines)
            print(output_stdout)
        elif input == 'q':
            exit(0)


if __name__ == '__main__':
    main()
