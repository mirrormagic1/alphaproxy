# alphaproxy
alphaproxy is a simple HTTP proxy that implements the old Minecraft authentication protocol using the newer Microsoft auth services. 

It requires a recent version of Python 3 and the `requests` library.

## How to run
To run on the default port (8444):
```
python3 main.py
```

To run on custom port:
```
python3 main.py 12345
```

## How to use
You'll need to configure the JVM arguments for your game to configure Java to use the proxy server:
```
-Dhttp.proxyHost=<host> -Dhttp.proxyPort=<port>
```
Replace `<host>` and `<port>` with the address and port of your proxy server, respectively.

For Minecraft clients, this can be configured under "More options" in the "Edit installation" page, e.g.:
![](https://drinkybird.s3.eu-west-1.amazonaws.com/ShareX/20211209_201146.png)
For Minecraft servers, just add the parameters to your command line before the `-jar`, e.g.: 
```
java -Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=8444 -jar minecraft_server.jar nogui
```
