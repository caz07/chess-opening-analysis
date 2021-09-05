from mysql import connector
from mysql.connector import errorcode
import os

class Db:
    def __init__(self):
        # Connect to db, inspired by https://github.com/CatCookie/DomainSearch/blob/master/src/additional/database.py
        # and https://dev.mysql.com/doc/connector-python/en/connector-python-example-connecting.html

        try:
            # Code from https://stackoverflow.com/questions/58633300/how-to-create-a-dictionary-from-os-environment-variables
            config = {
                'host':'DB_HOST',
                'user':'DB_USER',
                'password':'DB_PASS',
                'database':'CHESS_DB_NAME'
            }
            db_config = {k: os.getenv(v) for k,v in config.items()
             if v in os.environ}

            self._cnx = connector.connect(**db_config)
            self.cursor = self._cnx.cursor(buffered=True, dictionary=True)
        except connector.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                print("Something is wrong with your username or password")
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                print("Database does not exist")
            else:
                print(err)
                
            self._cnx.close()

    def execute(self, query, arguments = None):
        results = []
        for result in self.cursor.execute(query, arguments, multi=True):
            if result.with_rows:
                results.append(result.fetchall())
                
        self._cnx.commit()
        return results[0] if results else None

    def close_connection(self):
        self._cnx.close()
        self.cursor.close()

    def get_cursor(self):
        return self.cursor
