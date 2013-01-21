###
# Copyright (c) 2013, Pierre-Francois Carpentier
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

import os
import time
from lxml import etree
import threading
import md5
import unicodedata
import datetime
import itertools
import supybot.utils as utils
import supybot.ircdb as ircdb
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.ircmsgs as ircmsgs
import supybot.world as world

class SqliteSeLogerDB(object):
    """This Class is the backend of the plugin,
    it handles the database, its creation, its updates,
    it also provides methods to get the add information
    """

    #the elements we get from the xml
    def __init__(self, log, filename='db.seloger'):
        self.dbs = ircutils.IrcDict()
        self.filename = filename
        self.log=log
        self.val_xml = (
            'idTiers', 
            'idAnnonce',
            'idPublication', 
            'idTypeTransaction', 
            'idTypeBien',
            'dtFraicheur', 
            'dtCreation', 
            'titre', 
            'libelle', 
            'proximite', 
            'descriptif', 
            'prix',
            'prixUnite', 
            'prixMention', 
            'nbPiece', 
            'nbChambre', 
            'surface', 
            'surfaceUnite', 
            'idPays', 
            'pays', 
            'cp', 
            'ville', 
            'nbPhotos',
            'firstThumb',
            'permaLien',
            'latitude',
            'longitude',
            'llPrecision'
        )
 
        self.val_xml_count = len(self.val_xml)
        self.primary_key = 'idAnnonce'

    def _dict_factory(cursor, row):
        """just a small trick to get returns from the
        searches inside the database as dictionnaries
        """
        d = {}
        for idx,col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def close(self):
        """function closing the database cleanly
        """
        for db in self.dbs.itervalues():
            db.close()

    def _getDb(self):
        """this function returns a database connexion, if the
        database doesn't exist, it creates it.
        """
        try:
            import sqlite3
        except ImportError:
            raise callbacks.Error, 'You need to have PySQLite installed to ' \
                                   'use Poll.  Download it at ' \
                                   '<http://pysqlite.org/>'
        filename = 'db.seloger'

        if filename in self.dbs:
            return self.dbs[filename]
        if os.path.exists(filename):
            self.dbs[filename] = sqlite3.connect(
                filename, check_same_thread = False
                )

            return self.dbs[filename]
        db = sqlite3.connect(filename, check_same_thread = False)
        self.dbs[filename] = db
        cursor = db.cursor()

        #initialisation of the searches table 
        #(contains the searches entered by each user) 
        #search_id: the id of the search 
        #owner_id: the id of the user who entered the search
        #flag_active: a flag set to 1 when the search is active, 
        #             0 when it's not (not in use)
        #cp: the postal code
        #min_surf: minimum surface of the annonce
        #max_price: maximum rent
        cursor.execute("""CREATE TABLE searches (
                          search_id TEXT PRIMARY KEY,
                          owner_id TEXT, 
                          flag_active INTEGER,
                          cp TEXT,
                          min_surf TEXT,
                          max_price TEXT,
                          UNIQUE (search_id) ON CONFLICT IGNORE)"""
                      )

        #mapping between a search result and a user (n to n mapping)
        #idAnnonce: the id of on annonce
        #owner_id: the id of an owner
        #flag_shown: a flag set to 0 when the annonce was already 
        #           presented to owner_id, 0 if not
        cursor.execute("""CREATE TABLE map (
                          uniq_id TEXT PRIMARY KEY,
                          idAnnonce TEXT,
                          flag_shown INT,
                          owner_id TEXT,
                          UNIQUE (uniq_id) ON CONFLICT IGNORE)"""
                      )
        
        #generate the string of table fields from self.val_xml
        table_results = ''
        for val in self.val_xml:
            if val == self.primary_key:
                table_results = table_results + val \
                                + ' TEXT PRIMARY KEY, '
            else:
                table_results = table_results + val \
                                + ' TEXT, '

        #the table containing the information of an annonce
        cursor.execute("""CREATE TABLE results (
                          %s
                          UNIQUE (idAnnonce)ON CONFLICT IGNORE)""" % table_results )
        db.commit()
        self.log.info('database %s created',filename)
        return db

    def _get_annonce(self, idAnnonce):
        """backend function getting the information of one add 
        """
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        cursor.execute(
            """SELECT * FROM results WHERE idAnnonce = (?)""",
            (idAnnonce, )
            )
        return cursor.fetchone()

    def _search_seloger(self, cp, min_surf, max_price, owner_id):
        """entry function for a search
        cp: the postal code
        min_surface: the minimal surface
        max_price: the maximum rent

        """
        owner_id.lower() 
        url = 'http://ws.seloger.com/search.xml?cp=' + cp + \
        '&idqfix=1&idtt=1&idtypebien=1,2&px_loyerbtw=NAN%2f' + max_price + \
        '&surfacebtw=' + min_surf + '%2fNAN&SEARCHpg=1'

        while url is not None:
                url = self._get(url, owner_id)

    def _get(self, url, owner_id):
        """
        function searching getting the xml pages (recursively) and putting
        the results inside the database
        url: the url giving the nice xml
        """
        owner_id.lower() 
        db = self._getDb()
        cursor = db.cursor()

        #we try to load the xml page
        try:
            tree = etree.parse(url)
        except:
            self.log.warning('could not download %s',url)
            return None

        root = tree.getroot()
        annonces = root.find('annonces')

        for annonce in annonces:
            values_list=[]
            for val in self.val_xml:
                if annonce.find(val) is None or annonce.find(val).text is None:
                    values_list.append(u'Unknown')
                else:
                    values_list.append(unicode(annonce.find(val).text))

            #inserting the add information inside the table
            cursor.execute(
                    "INSERT INTO results VALUES (" + \
                        ','.join(itertools.repeat('?', self.val_xml_count)) + ")", 
                    tuple(values_list)
                    )

            annonce_id = annonce.find('idAnnonce').text

            #calcul of the uniq id for the mapping between 
            #the searcher and the add
            uniq_id = md5.new(owner_id + annonce_id).hexdigest()

            #inserting the search inside
            cursor.execute("INSERT INTO map VALUES (?,?,?,?)",\
                    (uniq_id, annonce_id, '1', owner_id ))
            db.commit()

        #if there is another page of search, we send return it, None otherwise
        if tree.xpath('//recherche/pageSuivante'):
            return  tree.xpath('//recherche/pageSuivante')[0].text
        else:
            return None

    def add_search(self, owner_id, cp, min_surf, max_price):
        """this function adds a search inside the database
        """
        owner_id.lower() 
        db = self._getDb()
        cursor = db.cursor()

        search_id = md5.new(owner_id + cp + min_surf + max_price).hexdigest()

        cursor.execute("INSERT INTO searches VALUES (?, ?, ?, ?, ?, ?)",
            (search_id, owner_id, '1', cp, min_surf, max_price)
            )

        db.commit()

        self.log.info('%s has added a new search', owner_id)
        return search_id

    def do_searches(self):
        """This function query SeLoger for new adds to put inside the database
        """
        self.log.info('refreshing database')
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        cursor.execute("SELECT * FROM searches WHERE flag_active = 1")

        for row in cursor.fetchall():
            self._search_seloger(
                row['cp'],row['min_surf'],row['max_price'],row['owner_id']
                )

    def disable_search(self, search_id, owner_id):
        """ this function permits to disable a search
        """
        self.log.info('disabling search %s',search_id)
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        cursor.execute(
            "DELETE FROM searches WHERE search_id = (?) AND owner_id = (?)",
            (search_id, owner_id)
            )
        db.commit()

    def get_search(self, owner_id):
        """ this function returns the search of a given user
        """
        self.log.info('printing search list of %s', owner_id)
        owner_id.lower() 
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        cursor.execute(
            """SELECT * FROM searches WHERE owner_id = (?) AND flag_active = 1""",
            (owner_id, )
            )

        return cursor.fetchall()

    def get_new(self):
        """ this function returns the adds not already printed
        and marks them as "printed".
        """
        self.log.info('printing new adds')
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        cursor.execute("SELECT * FROM map WHERE flag_shown = 1")

        return_annonces=[]
        for row in cursor.fetchall():
            uniq = row['uniq_id']
            cursor.execute(
                """UPDATE map SET flag_shown = 0 WHERE uniq_id = (?)""",
                (uniq, )
                )
            result = self._get_annonce(row['idAnnonce'])
            result['owner_id'] = row['owner_id']
            return_annonces.append(result)

        db.commit()
        return return_annonces

class SeLoger(callbacks.Plugin):
    """This plugin search and alerts you in query if 
    new ads are available.
    Use "sladd" for a new search.
    Use "sllist" to list you current search.
    Use "sldisable" to remove an old search."""
    threaded = True

    def __init__(self,irc):
        self.__parent = super(SeLoger, self)
        self.__parent.__init__(irc)
        self.backend = SqliteSeLogerDB(self.log)
        self.gettingLockLock = threading.Lock()
        self.locks = {}

    ### the external methods

    def sladd(self, irc, msg, args, pc, min_surf, max_price):
        """add <postal code> <min surface> <max price>
        Adds a new search for you
        """
        user = irc.msg.nick 
        self._addSearch(str(user), str(pc), str(min_surf), str(max_price))
        msg='Done sladd'
        irc.reply(msg,to=user,private=True)

    sladd = wrap(sladd, ['int', 'int', 'int'])

    def sldisable(self, irc, msg, args, id_search):
        """disable <id_search>
        Disables a search
        """
        user = irc.msg.nick
        self._disableSearch(user, id_search)
        msg='Done sldisable'
        irc.reply(msg,to=user,private=True)
    sldisable = wrap(sldisable, ['text'])

    def sllist(self, irc, msg, args):
        """list
        list all your searches
        """
        user = irc.msg.nick 
        self._listSearch(user, irc)
        msg='Done sllist'
        irc.reply(msg,to=user,private=True)

    sllist = wrap(sllist)

    ### The internal methods

    def __call__(self, irc, msg):
        """black magic...at least for me
        """
        self.__parent.__call__(irc, msg)
        irc = callbacks.SimpleProxy(irc, msg)
        t = threading.Thread(None,self._print, None, (irc,))
        t.start()

    def _update_db(self):
        """direct call to do_search from the backend class
        it gets the new adds from SeLoger
        """
        self.backend.do_searches()

    def _acquireLock(self, url, blocking=True):
        """Lock handler for the threads
        """
        try:
            self.gettingLockLock.acquire()
            try:
                lock = self.locks[url]
            except KeyError:
                lock = threading.RLock()
                self.locks[url] = lock
            return lock.acquire(blocking=blocking)
        finally:
            self.gettingLockLock.release()

    def _releaseLock(self, url):
        """Lock handler for the threads
        """
        self.locks[url].release()

    def _print(self,irc):
        """This function updates the database 
        and prints any new results to each user
        """
        if self._acquireLock('print', blocking=False):
            self._update_db()
            for add in self.backend.get_new():
                self._print_add(add,irc)
            time.sleep(120)
            self._releaseLock('print')

    def _reformat_date(self, date):
        """small function reformatting the date format from SeLoger
        """
        d = datetime.datetime.strptime(date, '%Y-%m-%dT%H:%M:%S')
        return  d.strftime('%d/%m/%Y %H:%M')

    def _print_add(self,add,irc):
        """this function prints one add
        """
        user = str(add['owner_id'])
        msg = ' '
        irc.reply(msg,to=user,private=True)

        price = ircutils.mircColor('Prix: ' + add['prix'] + add['prixUnite'], 8)
        rooms  = ircutils.mircColor('Pieces: ' + add['nbPiece'],4) 
        surface =  ircutils.mircColor(
                        'Surface: ' + add['surface'] + add['surfaceUnite'],
                        13
                        )

        msg = price + ' | ' + rooms + ' | ' + surface
        irc.reply(msg,to=user,private=True)

        city = ircutils.mircColor('Ville: ' + add['ville'], 11)  
        cp = ircutils.mircColor('Code postal: ' + add['cp'], 12) 
        date = ircutils.mircColor(
                   'Date ajout: ' + self._reformat_date(add['dtCreation']), 
                   11
                   )

        msg = city + ' | ' + cp + ' | ' + date
        irc.reply(msg,to=user,private=True)

        msg = ircutils.mircColor(
                    'Localisation: https://maps.google.com/maps?q=' \
                            + add['latitude'] + '+' + add['longitude'], 
                    3
                    )
        irc.reply(msg,to=user,private=True)


        msg = ircutils.mircColor('Proximite: ' + add['proximite'],2)
        irc.reply(msg,to=user,private=True)

        msg = u'Description: ' + add['descriptif']
        msg = unicodedata.normalize('NFKD',msg).encode('ascii','ignore')
        irc.reply(msg,to=user,private=True)

        msg = ircutils.mircColor('Lien: ' + add['permaLien'],9)
        irc.reply(msg,to=user,private=True)
        msg =  ' '
        irc.reply(msg,to=user,private=True)

        self.log.debug('printing add %s of %s ', add['idAnnonce'], user)
 
    def _addSearch(self, user, pc, min_surf, max_price):
        """this function adds a search"""
        self.backend.add_search(user, pc, min_surf, max_price)

    def _disableSearch(self, user, id_search):
        """this function disables a search"""
        self.backend.disable_search(id_search,user)

    def _listSearch(self, user, irc):
        """this function list the current searches"""
        searches = self.backend.get_search(user)
        for search in searches:
            id_search = ircutils.mircColor("ID: " + search['search_id'], 8)
            surface = ircutils.mircColor("Surface >= " + search['min_surf'], 4)
            loyer = ircutils.mircColor("Loyer <= " + search['max_price'], 13)
            cp = ircutils.mircColor("cp == " + search['cp'], 11)
            msg = id_search + " | " + surface + " | " + loyer + " | " + cp
            irc.reply(msg,to=user,private=True)

Class = SeLoger

# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
