#!/usr/bin/env python
#
# Kerberos login to IMAP server and extraction of provided cid: and mid: URIs.
#
# From: Rick van Rein <rick@openfortress.nl>


import os
import sys
from base64 import b64encode, b64decode
import imaplib
import urllib

import kerberos


class SASLTongue:

	def __init__ (self):
		self.ctx = None
		self.complete = False

	def wrap (self, plaintext):
		"""Once a GSSAPI Context is complete, it can wrap plaintext
		   into ciphertext.  This function operates on binary strings.
		"""
		kerberos.authGSSClientWrap (self.ctx, b64encode (plaintext))
		cipherdata = kerberos.authGSSClientResponse (self.ctx)
		return (b64decode (cipherdata) if cipherdata else "")

	def unwrap (self, ciphertext):
		"""Once a GSSAPI Context is complete, it can unwrap ciphertext
		   into plaintext.  This function operates on binary strings.
		"""
		kerberos.authGSSClientUnwrap (self.ctx, b64encode (ciphertext))
		return b64decode (kerberos.authGSSClientResponse (self.ctx))

	def processor (self, hostname):
		# Currying function (needed to bind 'self')
		def step (rcv):
			#DEBUG# print 'New Call with Complete:', self.complete
			#DEBUG# print 'Received:', '"' + b64encode (rcv) + '"'
			if not self.complete:
				# Initiate the GSSAPI Client
				#ALT# rc, self.ctx = kerberos.authGSSClientInit ('imap@' + hostname, gssflags=kerberos.GSS_C_SEQUENCE_FLAG)
				#STD# rc, self.ctx = kerberos.authGSSClientInit ('imap@' + hostname)
				if not self.ctx:
					rc, self.ctx = kerberos.authGSSClientInit ('imap@' + hostname)
				rc = kerberos.authGSSClientStep (self.ctx, b64encode (rcv))
				#DEBUG# print 'ClientStep Result Code:', ['CONTINUE', 'COMPLETE'] [rc]
				if rc == kerberos.AUTH_GSS_COMPLETE:
					self.complete = True
				# if rc != 0:
				# 	print 'Error making a step'
				# 	return None
				snd = kerberos.authGSSClientResponse (self.ctx)
				return (b64decode (snd) if snd else "")
			else:
				# Unwrap and interpret the information token
				rc = kerberos.authGSSClientUnwrap (self.ctx, b64encode (rcv))
				# if rc != 0:
				# 	print 'Error unwrapping'
				# 	return None
				token = b64decode (kerberos.authGSSClientResponse (self.ctx))
				if len (token) != 4:
					#DEBUG# print 'Error unwrapping token after GSSAPI handshake'
					return None
				flags = ord (token [0])
				#DEBUG# print 'Flags:', '0x%02x' % flags
				if flags & kerberos.GSS_C_INTEG_FLAG:
					pass #DEBUG# print 'Integrity Supported'
				if flags & kerberos.GSS_C_CONF_FLAG:
					pass #DEBUG# print 'Confidentialtiy Supported'
				maxlen = (ord (token [1]) << 16) | (ord (token [2]) << 8) | (ord (token [3]))
				#DEBUG# print 'Maxlen:', maxlen
				rettok = (chr (0) * 4) + 'ofo'
				return self.wrap (rettok)
				# kerberos.authGSSClientWrap (self.ctx, b64encode (rettok))
				# snd = kerberos.authGSSClientResponse (self.ctx)
				# return (b64decode (snd) if snd else "")

		# The Currying surroundings return the internal function
		# This is a strange necessity due to the IMAP assumption
		# that it can call a closure, or a stateless function.
		# What a lot of work to evade global variables... and it's
		# all due to an ill-designed API, I think.
		return step

	def clientname (self):
		return kerberos.authGSSClientUserName (self.ctx)



#
# Check the commandline
#
if len (sys.argv) < 2:
	sys.stderr.write ('Usage: ' + sys.argv [0] + ' mid:... cid:...\n\tTo retrieve the mid: and/or cid: URIs from your IMAP mailbox\nAuthentication and mailbox identities use your current Kerberos ticket\n')
	sys.exit (1)

#
# Turn the commandline into (messageid,contentid) pairs
#
todo = [ ]
def alsodo (todo, mid=None, cid=None):
	if mid:
		mid = '<' + urllib.unquote (mid) + '>'
	if cid:
		cid = '<' + urllib.unquote (cid) + '>'
	todo.append ( (mid,cid) )

for arg in sys.argv [1:]:
	if arg [:4].lower () == 'mid:':
		slashpos = arg.find ('/')
		if slashpos > 0:
			alsodo (todo, mid=arg [4:slashpos], cid=arg [slashpos+1:])
		else:
			alsodo (todo, mid=arg [4:])
	elif arg [:4].lower () == 'cid:':
		alsodo (todo, cid=arg [4:])
	else:
		sys.stderr.write ('You should only use mid:... and cid:... arguments, see RFC 2392\n')
		sys.exit (1)
	#DEBUG# print 'Searching for', todo [-1]

remote_hostname = 'popmini.opera'

im = imaplib.IMAP4 (remote_hostname, 143)
authctx = SASLTongue ()
authcpu = authctx.processor (remote_hostname)
#DEBUG# print 'AuthCPU:', authcpu, '::', type (authcpu)
im.authenticate ('GSSAPI', authcpu)

print 'Accessing IMAP as', authctx.clientname ()

ok,msgs = im.select ()
if ok != 'OK':
	sys.stderr.write ('Failed to select INBOX\n')
	sys.exit (1)

for (mid,cid) in todo:
	#DEBUG# print 'Retrieving', (mid,cid)
	if mid:
		# This is relatively quick, Content-ID is much slower, even
		# as an _added_ conition (huh... Dovecot?!?)
		cc = '(HEADER Message-ID "' + mid + '")'
	else:
		# Strange... no MIME-header search facilities in IMAP4rev1?!?
		cc = '(TEXT "' + cid + '")'
	#DEBUG# print 'Search criteria:', cc
	ok,findings = im.uid ('search', None, cc)
	if ok != 'OK':
		sys.stderr.write ('Failed to search\n')
		sys.exit (1)
	#DEBUG# print 'Found the following:', findings
	for uid in findings:
		#DEBUG# print 'Looking up UID', uid
		ok,data = im.uid ('fetch', uid, 'BODYSTRUCTURE')
		if ok != 'OK':
			sys.stderr.wrote ('Error fetching body structure')
			sys.exit (1)
		#DEBUG# print 'Found', data
		stack = [ ]
		parsed = [ ]
		if not data [0]:
			sys.stderr.write ('Failed to locate content\n')
			sys.exit (1)
		unquoted = data [0].split ('"')
		for i in range (len (unquoted)):
			if i & 0x0001 == 0:
				# Even entries are unquoted
				w = unquoted [i]
				modulus = len (w) + 3
				while w != '':
					brapos = min (w.find ('(') % modulus, w.find (')') % modulus, w.find (' ') % modulus)
					if brapos > 0:
						if w [:brapos] == 'NIL':
							parsed.append (None)
						else:
							parsed.append (w [:brapos])
					if w [brapos] == '(':
						# Push on stack
						stack.append (parsed)
						parsed = [ ]
					if w [brapos] == ')':
						# Pop from stack
						tail = parsed
						parsed = stack.pop ()
						parsed.append (tail)
					w = w [brapos+1:]
			else:
				# Quoted word -- pass literally
				parsed.append (unquoted [i])
		# print 'Parsed it into', parsed
		bodystructure = parsed [1] [3]
		#DEBUG# print 'Body structure:', bodystructure
		def printbody (bs, indents=0):
			subs = True
			for i in range (len (bs)):
				if type (bs [i]) == type ([]):
					if subs:
						printbody (bs [i], indents=indents+1)
					else:
						print '  ' * indents + '{%02d}' % i
				else:
					# subs = False
					print '  ' * indents + '[%02d]' % i, bs [i]
		#DEBUG# printbody (bodystructure)
		
		def matchcid (bs, cid, accupar, path=[]):
			subs = True
			for i in range (len (bs)):
				if type (bs [i]) == type ([]):
					if subs:
						matchcid (bs [i], cid, accupar, path=path+[i])
				else:
					if i == 3:
						pass #DEBUG# print 'Comparing', cid, 'with', bs [i]
					if i == 3 and bs [i] == cid:
						#DEBUG# print 'CID found on:', path
						accupar.append (path)
					subs = False
		if cid:
			accu = []
			matchcid (bodystructure, cid, accu, path=[1,3])
			#DEBUG# print 'Result is:', accu
			absname = cid [1:-2]
		else:
			accu = [[1,3,1]]
			absname = mid [1:-2]
		for result in accu:
			here = parsed
			for i in result:
				here = here [i]
			print 'MIME-Type =', here [0] + '/' + here [1]
			print '[attr,value,...] =', here [2]
			name = None
			for i in range (0, len (here [2]), 2):
				print 'Looking for name in', here [2][i]
				if here [2][i].lower () == 'name':
					name = here [2][i+1]
			print 'Filename:', name
			print 'Content-ID =', here [3] if len (here) > 3 else ''
			print 'Description =', here [4] if len (here) > 4 else ''
			print 'Transfer-Encoding =', here [5] if len (here) > 5 else ''
			encoding = here [5] if len (here) > 5 else ''
			print 'Size =', here [6] if len (here) > 6 else '?'
			bodyspec = 'BODY'
			dot = '['
			for r in result [2:]:
				bodyspec = bodyspec + dot + str (r+1)
				dot = '.'
			bodyspec = bodyspec + ']'
			if bodyspec == 'BODY]':
				bodyspec = 'BODY[1]'
			print 'Fetchable bodyspec', bodyspec, 'for UID', uid
			ok,data = im.uid ('fetch', uid+':'+uid, '('+bodyspec+')')
			if ok != 'OK':
				sys.stderr.write ('Error fetching content')
				sys.exit (1)
			#TODO# Be more subtle about encoding lists
			if os.path.exists (absname):
				sys.stderr.write ('Fatal: file ' + absname + ' already exists\nYou probably ran the command twice; or else the sender may attempt overwriting\n')
				sys.exit (1)
			fh = open (absname, 'wb')
			if encoding == 'base64':
				fh.write (b64decode (data [0][1]))
			else:
				fh.write (data [0][1])
			fh.close ()
			print 'Written to:', absname
			if name:
				if not os.path.exists (name):
					os.link (absname, name)
					print 'Created a link from:', name
				else:
					sys.stderr.write ('Warning: file ' + name + ' already exists, not linking\n')


