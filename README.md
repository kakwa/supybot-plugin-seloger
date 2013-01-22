supybot-plugin-seloger
======================

supybot plugin for seloger

## Description ##

This supybot plugin searches and alerts you in query for any new adds on 
the french website "www.seloger.com".

## License ##

See the plugin files.

## Screenshot ##

Here is the result inside irssi:

<img src="https://raw.github.com/kakwa/supybot-plugin-seloger/master/screenshot/seloger-screenshot.jpg"/>

## Dependancies ##

This plugin relies on:

* supybot
* lxml
* sqlite3
* python2

## Commands ##

Here is the commands list: 

* ```sladd <postal code> <min surface> <max price>```: add a new search for you
* ```sllist```: list your active searches
* ```sldisable <search ID>```: remove the given search

This plugin replies you and sends you new adds in query.

## Installation ##

This section explains how to install supybot 
(given that you already have git and the dependancies installed)

It might also be a good idea to create a dedicated user for supybot.

Here are the commands to create a supybot from scratch with this plugin:

```shell
$ mkdir mybot/
$ cd mybot/
$ supybot-wizard #answer the questions (install it in the default directory (./))
$ git clone https://github.com/kakwa/supybot-plugin-seloger.git plugins/SeLoger/
$ sed -i 's/\(supybot.plugins:.*\)/\1\ SeLoger/' *.conf
$ echo "supybot.plugins.SeLoger: True" >>*.conf
$ echo "supybot.plugins.SeLoger.public: True" >>*.conf
$ screen supybot *.conf
```
