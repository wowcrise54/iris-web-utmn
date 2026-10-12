#  IRIS Source Code
#  Copyright (C) 2021 - Airbus CyberSecurity (SAS)
#  ir@cyberactionlab.net
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
import logging

from app import app as iris_app
from app import asgi_app as app

if __name__ != '__main__':
    server_logger = logging.getLogger('uvicorn.error')
    for handler in server_logger.handlers:
        iris_app.logger.addHandler(handler)
    iris_app.logger.setLevel(logging.INFO)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run('run:app', host='127.0.0.1', port=8000)

