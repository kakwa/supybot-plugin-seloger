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

import supybot.utils as utils
import supybot.ircdb as ircdb
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
#import supybot.dbi as dbi

#the elements we get from the xml
val_xml = ( 
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

def dict_factory(cursor, row):
    d = {}
    for idx,col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class SqliteSeLogerDB(object):


    def __init__(self, filename='db.seloger'):
        self.dbs = ircutils.IrcDict()
        self.filename = filename

    def close(self):
        for db in self.dbs.itervalues():
            db.close()

    def _getDb(self):
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
            self.dbs[filename] = sqlite3.connect(filename, check_same_thread = False)
            return self.dbs[filename]
        db = sqlite3.connect(filename, check_same_thread = False)
        self.dbs[filename] = db
        cursor = db.cursor()

        #initialisation of the searches table (contains the searches entered by each user) 
        #search_id: the id of the search 
        #owner_id: the id of the user who entered the search
        #flag_active: a flag set to 1 when the search is active, 0 when it's not (not in use)
        #cp: the postal code
        #min_surf: minimum surface of the annonce
        #max_price: maximum rent
        cursor.execute("""CREATE TABLE searches (
                          search_id INTEGER PRIMARY KEY,
                          owner_id TEXT, 
                          flag_active INTEGER,
                          cp TEXT,
                          min_surf TEXT,
                          max_price TEXT,
                          UNIQUE (search_id) ON CONFLICT IGNORE)""")

        #mapping between a search result and a user (n to n mapping)
        #idAnnonce: the id of on annonce
        #owner_id: the id of an owner
        #flag_shown: a flag set to 0 when the annonce was already presented to owner_id, 0 if not
        cursor.execute("""CREATE TABLE map (
                          uniq_id TEXT PRIMARY KEY,
                          idAnnonce TEXT,
                          flag_shown INT,
                          owner_id TEXT,
                          UNIQUE (uniq_id) ON CONFLICT IGNORE)""")

        #the table containing the information of an annonce
        cursor.execute("""CREATE TABLE results (
                          idTiers TEXT,
                          idAnnonce TEXT PRIMARY KEY,
                          idPublication TEXT,
                          idTypeTransaction TEXT,
                          idTypeBien TEXT,
                          dtFraicheur TEXT,
                          dtCreation TEXT,
                          titre TEXT,
                          libelle TEXT,
                          proximite TEXT,
                          descriptif TEXT,
                          prix TEXT,
                          prixUnite TEXT,
                          prixMention TEXT,
                          nbPiece TEXT,
                          nbChambre TEXT,
                          surface TEXT,
                          surfaceUnite TEXT,
                          idPays TEXT,
                          pays TEXT,
                          cp TEXT,
                          ville TEXT,
                          nbPhotos TEXT,
                          firstThumb TEXT,
                          permaLien TEXT,
                          latitude TEXT,
                          longitude TEXT,
                          llPrecision TEXT,
                          UNIQUE (idAnnonce)ON CONFLICT IGNORE)""")
        db.commit()
        return db

    def _get_annonce(self, idAnnonce):
        db = self._getDb()
        db.row_factory = dict_factory
        cursor = db.cursor()
        cursor.execute("""SELECT * FROM results WHERE idAnnonce = (?)""", (idAnnonce, ))
        return cursor.fetchone()

    def _search_seloger(self, cp, min_surf, max_price, owner_id):
        """entry function for a search
        cp: the postal code
        min_surface: the minimal surface
        max_price: the maximum rent

        """
        
        self._get_and_get_next('http://ws.seloger.com/search.xml?cp=' + cp + \
        '&idqfix=1&idtt=1&idtypebien=1,2&px_loyerbtw=NAN%2f' + max_price + \
        '&surfacebtw=' + min_surf + '%2fNAN&SEARCHpg=1', owner_id)

    def _get_and_get_next(self, url, owner_id):
        """
        function searching getting the xml pages (recursively) and putting
        the results inside the database
        url: the url giving the nice xml
        """
        db = self._getDb()
        cursor = db.cursor()
        tree = etree.parse(url)
        root = tree.getroot()
        annonces = root.find('annonces')

        for annonce in annonces:
            values_list=[]
            for val in val_xml:
                if annonce.find(val) is None or annonce.find(val).text is None:
                    values_list.append('Unknown')
                else:
                    values_list.append(annonce.find(val).text)
            cursor.execute("INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", tuple(values_list))
            annonce_id = annonce.find('idAnnonce').text
            uniq_id = str(annonce_id) + 'Z' + str(owner_id)
            cursor.execute("INSERT INTO map VALUES (?,?,?,?)", (uniq_id, annonce_id, '1', owner_id ))
            db.commit()

        if tree.xpath('//recherche/pageSuivante'):
            self._get_and_get_next(tree.xpath('//recherche/pageSuivante')[0].text)




    def add_search(self, owner_id, cp, min_surf, max_price):
        db = self._getDb()
        cursor = db.cursor()
        cursor.execute("SELECT MAX(search_id) FROM searches")
        max_id = cursor.fetchone()
        if max_id[0] is not None:
            search_id = max_id[0] + 1
        else:
            search_id = 0

        cursor.execute("INSERT INTO searches VALUES (?, ?, ?, ?, ?, ?)", (search_id, owner_id, '1', cp, min_surf, max_price))
        db.commit()
        return search_id

    def do_searches(self):
        db = self._getDb()
        db.row_factory = dict_factory
        cursor = db.cursor()
        cursor.execute("SELECT * FROM searches WHERE flag_active = 1")

        #row = cursor.fetchone()
        #while row is not None:
        for row in cursor.fetchall():
            #print row
            self._search_seloger(row['cp'],row['min_surf'],row['max_price'],row['owner_id'])
            #row = cursor.fetchone()

    def disable_search(self, search_id):
        db = self._getDb()
        db.row_factory = dict_factory
        cursor = db.cursor()
        cursor.execute("UPDATE searches SET flag_active = 0 WHERE search_id = %s" % search_id)
        db.commit()

    def get_search(self, owner_id):
        db = self._getDb()
        db.row_factory = dict_factory
        cursor = db.cursor()
        cursor.execute("""SELECT * FROM searches WHERE owner_id = (?)""", (owner_id, ))
        return cursor.fetchall()


    def get_new(self):
        db = self._getDb()
        db.row_factory = dict_factory
        cursor = db.cursor()
        cursor.execute("SELECT * FROM map WHERE flag_shown = 1")

        #row = cursor.fetchone()
        #while row is not None:
        return_annonces=[]
        for row in cursor.fetchall():
            uniq = row['uniq_id']
            cursor.execute("""UPDATE map SET flag_shown = 0 WHERE uniq_id = (?)""", (uniq, ))
            result = self._get_annonce(row['idAnnonce'])
            result['owner_id'] = row['owner_id']
            return_annonces.append(result)

            #row = cursor.fetchone()

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
        self.backend = SqliteSeLogerDB()

    ### the external methods

    def sladd(self, irc, msg, args, pc, min_surf, max_price):
        """add <postal code> <min surface> <max price>
        Adds a new search for you
        """
        user = plugins.getUserName(self.by)
        self._addSearch(user, pc, min_surf, max_price)
        irc.reply('Done')
    sladd = wrap(sladd, [many('anything')])

        
    def sldisable(self, irc, msg, args, id_search):
        """disable <id_search>
        Disables a search
        """
        user = irc.msg.nick
        self._disableSearch(user, id_search)
        irc.reply('Done')
    sldisable = wrap(sldisable, [many('anything')])

 
    def sllist(self, irc, msg, args):
        """list
        list all your searches
        """
        user = irc.msg.nick #plugins.getUserName(self.by)
        self._listSearch(user, irc)
        irc.reply('Done')
    sllist = wrap(sllist)

    ### The internal methods

    def __call__(self, irc, msg):
        self.__parent.__call__(irc, msg)
        irc = callbacks.SimpleProxy(irc, msg)
        t = threading.Thread(None,self._update_and_print, None, (irc,))
        t.start()

    def _update_and_print(self,irc):
        self.backend.do_searches()
        for add in self.backend.get_new():
            self._print_add(add,irc)
        time.sleep(60)

    def _print_add(self,add,irc):
        irc.reply('>>>> NEW <<<<')
        irc.reply(add['idAnnonce'])
        irc.reply(add['descriptif'])


 
    def _addSearch(self, user, pc, min_surf, max_price):
        """this function adds a search"""
        self.backend.add_search(user, pc, min_surf, max_price)

    
    def _disableSearch(self, user, id_search):
        """this function disables a search"""
        self.backend.disable_search(id_search)


    def _listSearch(self, user, irc):
        """this function list the current searches"""
        searches = self.backend.get_search(user)
        for search in searches:
            irc.reply("ID: " + search['search_id'] + "=> surface >=" + search['min_surf'] + " rent <=" + search['max_price'] + " cp =" + search['cp'])

Class = SeLoger

#db=SqliteSeLogerDB()
#db._getDb()
#db.add_search('kakwa', '75014', '20', '800')
#db.add_search('kakwaa', '75014', '20', '800')
#db.disable_search('0')
#db.disable_search('1')
#db.disable_search('2')

#db.do_searches()
#print db.get_new()
#print db.get_search('kakwa')

# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
