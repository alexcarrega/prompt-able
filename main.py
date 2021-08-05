# Copyright (c) 2020 Alex Carrega <contact@alexcarrega.com>
# author: Alex Carrega <contact@alexcarrega.com>

import json
import threading
from datetime import datetime
from string import Template
from subprocess import PIPE, CompletedProcess, run
from typing import Dict, Iterable, List, Optional, Tuple, TypeVar

from bs4 import BeautifulSoup
from bunch import Bunch
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
        if not text.startswith(tuple(self.data.available_commands)):
            raise ValidationError(message=f'Command {text} not found')


def exec(command: str, args: str, data: Data) -> CompletedProcess[str]:
    data.last_exec_start = datetime.now()
    args = list(filter(lambda arg: arg.strip(), args))
    args_dict = {f'arg_{i}': v for i, v in enumerate(args, 1)}
    args_dict['args'] = '\n'.join(args)
    try:
        command = Template(command).substitute(**data.settings.get('vars', {}), **args_dict)
        output = run(command, check=False, shell=True,
                     stdout=PIPE, stderr=PIPE, universal_newlines=True)
    except KeyError as key_error:
        return Bunch(args=command, stdout=NOT_AVAILABLE, stderr=f'Variable not found: {key_error}', returncode=1)
    data.last_exec_end = datetime.now()
    data.last_exec_ret_code = output.returncode
    return output


def default(text: str) -> str:
    return text if text else NOT_AVAILABLE


def format(data: CompletedProcess[str], type: str, lines: bool) -> str:
    if type == 'html':
        output = BeautifulSoup(data.stdout, features='html5lib').prettify()
        output = highlight(output, lexers.HtmlLexer(), formatters.TerminalFormatter())
    if type == 'json':
        try:
            json_data = json.loads(data.stdout)
            output = json.dumps(json_data, indent=4, sort_keys=True)
            output = highlight(output, lexers.JsonLexer(), formatters.TerminalFormatter())
        except Exception as exception:

            output = f'\nError: {exception}\nInput: {data.args}\nOutput: {default(data.stdout)}\nMessage: {default(data.stderr)}\n'
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
    return lambda: HTML(f'<aaa fg="blue" bg="white"> - Time: <b>{data.last_exec_end}</b> </aaa><aaa fg="lightyellow"> - Duration: <b>{duration}</b> </aaa><aaa fg="dark{ret_code_style}" bg="white"> - Return code: <b>{data.last_exec_ret_code}</b> </aaa>')


def get_command(input: str, data: Data) -> Tuple[Optional[str], Optional[str]]:
    for cmd_key, cmd_data in data.settings.commands.items():
        if input.startswith(cmd_key):
            return (cmd_key, cmd_data)
    return (None, None)


def main():
    data = Data()
    session = PromptSession(history=FileHistory('.prompt-able'))

    while True:
        try:
            input = session.prompt(f'{data.settings.prompt} ',
                                   bottom_toolbar=bottom_toolbar(data),
                                   auto_suggest=AutoSuggestFromHistory(),
                                   completer=WordCompleter(data.available_commands),
                                   validator=CommandValidator(data),
                                   validate_while_typing=False).strip().lower()
            command_key, command_data = get_command(input, data)
            if command_data:
                type = command_data.output.strip().lower()
                lines = command_data.lines
                args = input.replace(command_key, '').split(' ')
                output_process = exec(command_data.exec, args, data)
                output = format(output_process, type, lines)
                print(output)
            elif input == 'q':
                exit(0)
        except KeyboardInterrupt or EOFError as err:
            print(err)


if __name__ == '__main__':
    main()
