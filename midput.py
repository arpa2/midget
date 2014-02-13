#!/usr/bin/env python
#
# Kerberos login to IMAP server and upload of provided files as a draft email.
#
# From: Rick van Rein <rick@openfortress.nl>


import os
import sys
from base64 import b64encode, b64decode
import imaplib
import urllib

import email.mime.base as mime
import email.mime.text as text
import email.mime.multipart as multipart

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


#
# Process the commandline
#
if len (sys.argv) < 2:
	sys.stderr.write ('Usage: ' + sys.argv [0] + ' attachment...\n\tThis command will create a draft email with the given files attached.\n')


attachments = [ ]
for arg in sys.argv [1:]:
	ana = os.popen ('file --mime-type "' + arg + '"').read ()
	(filenm,mimetp) = ana.split (': ', 1)
	(major,minor) = mimetp.strip ().split ('/', 1)
	filenm = arg.split (os.sep) [-1]
 	content = mime.MIMEBase (major, minor)
	content.set_param ('name', filenm)
	content.add_header ('Content-disposition', 'attachment', filename=filenm)
	attachments.append (content)


remote_hostname = 'popmini.opera'

#
# Login to IMAP
#
im = imaplib.IMAP4 (remote_hostname, 143)
authctx = SASLTongue ()
authcpu = authctx.processor (remote_hostname)
#DEBUG# print 'AuthCPU:', authcpu, '::', type (authcpu)
im.authenticate ('GSSAPI', authcpu)

#
# Select a mailbox for uploading to
#
draftbox = 'Drafts'
ok,msgs = im.select (draftbox)
if ok != 'OK':
	ok,msgs = im.select ()
	if ok == 'OK':
		sys.stderr.write ('Warning: No ' + draftbox + ' folder found, posting to INBOX\n')
		draftbox = 'INBOX'
	else:
		sys.stderr.write ('Failed to select both Drafts folder or even INBOX\n')
		sys.exit (1)


#
# Insert the content into the attachments
#
for (av,at) in zip (sys.argv [1:], attachments):
	if major == 'text':
		at.set_payload (           open (av, 'r').read () )
	else:
		at.set_payload (b64encode (open (av, 'r').read ()))

#
# Construct the email message to upload
#
introtxt = """Hello,

Attached, you will find 
"""
intro = text.MIMEText (introtxt)
attachments.insert (0, intro)

msg = multipart.MIMEMultipart ()
for at in attachments:
	msg.attach (at)

ok,data = im.append (draftbox, '(\\Flagged \\Draft)', None, msg.as_string ())
if ok != 'OK':
	sys.stderr.write ('Problem appending the file')
	sys.exit (1)
