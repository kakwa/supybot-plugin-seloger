supybot-plugin-seloger
======================

supybot plugin for seloger

### Description ###

This supybot plugin searches and alerts you in query for any new adds one the french website "seloger.com".

It's quite dirty but it works ;).

### License ###

See the plugin files.

### Screenshot ###

<img src="https://raw.github.com/kakwa/supybot-plugin-seloger/master/screenshot/seloger-screenshot.jpg" height="200" />


### Dependancies ###

This plugin relies on:

* supybot (...)
* lxml
* sqlite3
* python2

### Commands ###

* ```sladd <postal code> <min surface> <max price>```: add a new search for you
* ```sllist```: list your active searches
* ```sldisable <search ID>```: disable the given search

The bot replies and send new adds in query.
