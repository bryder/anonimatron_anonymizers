#!/usr/bin/env python
# The MIT License (MIT)
#
# Copyright (c) 2018 Bill Ryder
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import inspect
import json
import logging
import os

import sys

import datetime

import configargparse
import psycopg2
import psycopg2.extras

import jinja2
import jinja2.meta

script_path = os.path.realpath(__file__)
script_dir = os.path.dirname(script_path)
script_deploy_dir = os.path.dirname(script_dir)

script_etc_dir = os.path.join(script_deploy_dir, 'etc')
script_lib_dir = os.path.join(script_deploy_dir, 'lib')

script_path_no_ext = os.path.splitext(script_path)[0]


class JSONObjectEncoder(json.JSONEncoder):
    """
    Use this class to make almost any object json.dump able.

    use it like

    json.dumps(thing, cls=utils.ObjectEncoder)

    It will not dump any attribute prefixed with '_' or '__'

    """
    def default(self, obj):
        # DANGER: mock 2.0.0 will add the to_json attribute to magic mocked method.
        # it looks like there are fixes in the git repo but they are not released on PyPi
        # The workaround  is to only look for to_json on a class.
        if inspect.isclass(obj) and hasattr(obj, "to_json"):
            return self.default(obj.to_json())

        if isinstance(obj, dict):
            return obj
        elif isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.timedelta):
            return str(obj)
        elif isinstance(obj, set):
            return list(obj)
        else:
            d = dict()
            if hasattr(obj, '__dict__'):
                key_values = obj.__dict__.items()
            else:
                # for objects which do not have __dict__ you have to look at the members
                key_values = inspect.getmembers(obj)

            for key, value in key_values:
                # Note the NonCallableMagicMock test at the end - if you do not
                # do this if you json.dumps a mocked class then method_calls will pollute
                # your output when testing.
                if key.startswith("__") or key.startswith("_") \
                        or inspect.isabstract(value) \
                        or inspect.isbuiltin(value) \
                        or inspect.isfunction(value) \
                        or inspect.isgenerator(value) \
                        or inspect.ismethod(value) \
                        or inspect.isgeneratorfunction(value) \
                        or inspect.ismethoddescriptor(value) \
                        or inspect.isroutine(value) \
                        or key == 'method_calls' and 'NonCallableMagicMock' in str(type(obj)) :
                    pass
                else:
                    d[key] = value

            return self.default(d)


try:
    # This is only used in pycharm - it has stubs for this for python 2.7
    from typing import List, Optional, Dict, Any, AnyStr  # for type hinting
except Exception as exception_does_not_matter:
    pass

global_log = None


def setup_logger(log=None, name=None):
    if log is None:
        resolved_log = logging.getLogger(name)  # None means the root logger
        shandler = logging.StreamHandler(sys.stderr)
        shandler.setFormatter(
                logging.Formatter(
                        "%(levelname)-8s %(asctime)s %(filename)16s:%(funcName)s:%(lineno)-4d "
                        " %(message)s")
        )
        resolved_log.addHandler(shandler)
    else:
        resolved_log = log

    return resolved_log


def process_args(args_in, prog=None, log=None):

    ap = configargparse.ArgumentParser(
        description='generate a anonimatron xml config file for a database - WIP! ',
        prog=prog,
        formatter_class=configargparse.ArgumentDefaultsHelpFormatter,
        config_file_parser_class=configargparse.YAMLConfigFileParser)

    ap.add_argument(
        '-c', '--config', is_config_file=True,
        help="Put default arguments in this yaml file")

    ap.add_argument(
        "-d", "--debug", action="store_true",
        help="debug mode - will turn on verbose as well",)

    ap.add_argument(
        "-v", "--verbose", action="store_true",
        help="verbose mode")

    ap.add_argument(
        "--host",
        default='localhost',
        help='database hostname',
    )
    ap.add_argument(
        "--database",
        default='foreman',
        help='name of database'
    )
    ap.add_argument(
        "--user",
        default='foreman',
        help='database username',
    )
    ap.add_argument(
        "--password",
        default='foreman',
        help="database user password",
    )

    cli_args = ap.parse_args(args_in)

    log.setLevel(logging.WARNING)

    if cli_args.verbose:
        log.setLevel(logging.INFO)

    if cli_args.debug:
        log.setLevel(logging.DEBUG)

    log.info("Argument values: %s" % ap.format_values())
    log.info(
            "Resolved argument namespace %s" %
            json.dumps(
                    cli_args, indent=2,
                    cls=JSONObjectEncoder)
    )

    return cli_args

# language=XML
project_template = '''

<configuration salt="somethingsalty"
    jdbcurl="jdbc:postgresql://{{ host }}/{{ database }}" userid="{{ user }}" password="{{ password }}">
    <anonymizerclass>nz.billryder.anonimatron.anonymizer.DomainAnonymizer</anonymizerclass>
    
    
    {% for table in tables %}
    <table name="{{ table.name }}">
       {% for column in table.columns %}
        <column name="{{ column.name }}" type="{{ column.anon_type }}" size="{{ column.anon_size}}"/>
       {% endfor %}
    </table>
    {% endfor %}

</configuration>


'''

data_type_map = {
    'character varying': 'STRING',
    'integer': None,
    'text': 'STRING',
    'timestamp without time zone': None,
    'timestamp with time zone': None,
    'boolean': None,
    'xid': None,
    'smallint': None,
    'regproc': None,
    'real': None,
    'oid': None,
    'bigint': None,
    'double precision': None,
    'char': 'STRING',
    '"char"': 'STRING',
}


def get_table_names(conn, database_name, schema_name='public'):
    """

    :param conn: database connection
    :param str database_name:
    :return: list of table names
    :rtype: list[str]
    """

    tables = list()  # type: List[str]
    # table_catalog is the database name
    # table_schema
    with conn.cursor() as cursor:
        cursor.execute(
            '''
                SELECT tablename 
                FROM pg_catalog.pg_tables
                WHERE schemaname = %s AND tableowner = %s
                ORDER by tablename
            ''', (schema_name, database_name)
        )

        for table_row in cursor.fetchall():
            table_name = table_row[0]
            tables.append(table_name)

    return tables


def get_primary_keys(conn, schema, table):
    keys = list()

    with conn.cursor() as c:
        c.execute(
            '''
            SELECT column_name
            FROM information_schema.table_constraints
                 JOIN information_schema.key_column_usage
                     USING (constraint_catalog, constraint_schema, constraint_name,
                            table_catalog, table_schema, table_name)
            WHERE constraint_type = 'PRIMARY KEY'
              AND (table_schema, table_name) = (%s, %s)
            ORDER BY ordinal_position;
            ''',
            (schema, table)
        )
        for column_row in c.fetchall():
            keys.append(column_row[0])

    return keys


def get_check_template(body, provided_variables):
    """

    :param str body: template body
    :param provided_variables: variables that are provided
    :type provided_variables: Dict[str, Any]
    :return: jinja2.Template
    """

    env = jinja2.Environment()

    # Get the Abstract Syntax Tree for the template so variables can be checked
    ast = env.parse(body)

    required_variables = jinja2.meta.find_undeclared_variables(ast)
    missing_variables = required_variables - set(provided_variables.keys())

    if missing_variables:
        raise ValueError("Can not render the template - missing variables %s - provided variables %s" %
                         (",".join(missing_variables), ",".join(provided_variables.keys())))

    template = jinja2.Template(body, trim_blocks=True, lstrip_blocks=True)

    return template


class ColumnAction(object):
    def __init__(self, exclude=False, size=-1, anon_type=None):
        self.exclude = exclude
        self.size = size
        self.anon_type = anon_type


def main(args_in, prog=None, log=None):
    # This is done so when testing I can replace the logger - in some testing main() is run
    global global_log
    global_log = setup_logger(log=log)

    cli_args = process_args(args_in, prog=prog, log=global_log)

    conn = psycopg2.connect(
        host=cli_args.host,
        database=cli_args.database,
        user=cli_args.user,
        password=cli_args.password
    )

    schema = 'public'

    tables = list()  # type: List[Dict[str, Any]]
    exclude_tables = [
        'bloat_tables',
        'bloat_stats',
        'bloat_indexes',
        'dynflow_delayed_plans',  # anonimatron will not anonymise a table with no primary key so exclude this.
        #'notification_blueprints', # Exception in thread "main" java.lang.RuntimeException: org.postgresql.util.PSQLException: ERROR: syntax error at or near "group"
        'schema_migrations',    # no primary key - but also it's just a version number so not needed
    ]

    column_actions_by_table = {
        'auth_sources':
            {
                'type': ColumnAction(exclude=True),
                'attr_mail': ColumnAction(exclude=False, anon_type='EMAIL_ADDRESS'),
            },
        'domains':
            {
                'name': ColumnAction(exclude=False, anon_type='DOMAIN'),
                'fullname': ColumnAction(exclude=False, anon_type='DOMAIN'),
            },
        'fact_names':
            {
                'type': ColumnAction(exclude=True),
            }
    }

    default_column_action = ColumnAction(exclude=False, size=-1)

    for table_name in get_table_names(conn, cli_args.database):

        if table_name in exclude_tables:
            continue

        table = dict()
        table['columns'] = list()
        table['name'] = table_name

        primary_keys = set(get_primary_keys(conn, schema=schema, table=table_name))
        # table_catalog =
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                '''
                    SELECT * 
                    FROM information_schema.columns 
                    WHERE table_name = %s AND table_schema = %s AND table_catalog = %s
                ''',
                      (table_name, schema, cli_args.database))
            for column in c:
                db_data_type = column['data_type']
                column_name = column['column_name']
                column_action = default_column_action

                if table_name in column_actions_by_table:
                    if column_name in column_actions_by_table[table_name]:
                        column_action = column_actions_by_table[table_name][column_name]

                default_anon_type = data_type_map.get(db_data_type, None)
                anon_type = column_action.anon_type if column_action.anon_type else default_anon_type

                if anon_type and column_name not in primary_keys and not column_action.exclude:
                    column_desc = {
                        'name': column_name,
                        'db_data_type': db_data_type,
                        'anon_type': anon_type,
                        'anon_size': '-1',
                        'primary_key': column_name in primary_keys,
                    }
                    table['columns'].append(column_desc)
        if table['columns']:
            # anonimatron 1.9.3 will NullPointerException if no columns are listed
            tables.append(table)

    template_variables =  {
        'host': cli_args.host,
        'database': cli_args.database,
        'user': cli_args.user,
        'password': cli_args.password,
        'tables': tables
    }

    template = get_check_template(project_template, template_variables)

    print template.render(template_variables)


if __name__ == "__main__":
    global_log = setup_logger()
    main(sys.argv[1:], prog=None, log=global_log)
