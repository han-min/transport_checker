
# Introduction

## server.py
The main file for running the HTML server. This server has been split into 3 main chunk

### train_times_handler
`/api/trains` handling of train times. 

### bus_times_handler
`/api/bus` handling of bus stop times. Requires `TFL_APP_ID` and `TFL_APP_KEY`. You need to get it from `https://api-portal.tfl.gov.uk/`. Sign up with you email. Then under product subscribe for "500 Requests per min". After which, you will get two keys in your "Profile" in which you need to copy paste here.

### location_database_handler
`/api/proxy` private database connection and handling. You can ignore this.

## auth.py
Use this to keep the `PASSWORD_SALT` and `PASSWORD_HASH` generated using the `gen_hash.py`.
This is used for authentication on the webpage on access

## gen_hash.py
See `auth.py`
