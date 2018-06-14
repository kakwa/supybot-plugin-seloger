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

Here is the commands list with a few examples:

* `slhelp`: help for this module

```bash
slhelp
```

* `sladdrent <postal code> <min surface> <max price> <min_num_room>`: add a new rent search for you

```bash
<nickname> sladdrent 59000 20 600 1
<supyhome> Done sladd
```

* `sladdbuy <postal code> <min surface> <max price> <min_num_room>`: add a new buy search for you

```bash
<nickname> sladdbuy 75001 20 6000000000 10
<supyhome> Done sladd
```

* `sllist`: list your active searches

```bash
<nickname> sllist
<supyhome> ID: d5671b6f12ebee2449f307513f3c6322 | Surface >= 20 | Loyer <= 600 | cp == 59000 | type ad == 1 | Pieces >= 1
<supyhome> ID: 939262a37d935f4e6297de3a7afbf483 | Surface >= 20 | Loyer <= 6000000000 | cp == 75001 | type ad == 2 | Pieces >= 10
<supyhome> Done sllist
```

* `sldisable <search ID>`: remove the given search (use sllist to recover the <search ID>)


```bash
<nickname> sldisable 939262a37d935f4e6297de3a7afbf483 
```

* `slstatrent <postal code|'all'>`: print some stats about your rent searches

```bash
<nickname> slstatrent 59000
<supyhome> [...]
<supyhome> Done slstat
```

* `slstatbuy <postal code|'all'>`: print some stats about your buy searches

```bash
<nickname> slstatbuy all
<supyhome> [...]
<supyhome> Done slstat
```

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

And it should work, however, some servers could kick the bot for excess flood 
(it sends a lot of messages, specialy when adding new search), 
just change this parameter inside your bot configuration file:

```
supybot.protocols.irc.throttleTime: <float value>
```
