# Midget: Commandline interface to IMAP documents

> *The midget and midput commandline utilities let you download and
> upload email attachments from/to your IMAP mailbox, almost as if you
> are using SCP or a similar cross-platform copying command.*

You know about the shepherd boy who slayed a giant with his sling shot?
Keep reading...

## What is this?

Midget solves a problem that is so common that you might not have
noticed it. But it can really aid the automation of our daily tasks.

You probably recognise this workflow:

1.  You receive a document or package over email

2.  You save the attachment

3.  You move it to another system

4.  On that system, you process it further (unpackaging, saving,
    printing, …)

This flow can be greatly simplified. On the shell of the target machine,
you can simply run:

    midget mid:opq cid:stu mid:uvw/xyz...

This will retrieve documents with `mid:` or `cid:` URIs from your IMAP
account. These URIs are used to mark documents with a MIME-Type, and are
defined as pragmatically unique identities generated on the sending
site. They may occur in multiple places, but since these ought to be the
same only one will be retrieved by midget. MIME markings such as
filename proposals are taken into account; transport encoding is undone
but content encoding is not.

There is a counterpart to this command:

    midput file1 file2 file3

This will construct a new draft email in your IMAP account. The new
draft will have the given files as attachments. You can access the draft
in your graphical browser to enter what gave you the idea to send these
files.

## What is required to make this work?

These commands rely on Kerberos Single SignOn. Meaning, you are in a
shell account that shows a non-expired principal ticket when you run:

    klist

If not, logon to your REALM first, using:

    kinit

Your principal name is of the form `user@REALM` and midget and midput
interpret the REALM part as a DNS domain name. Under this domain name,
it will look for a `_kerberos` TXT record to confirm the case-sensitive
REALM value. Note that letters in this record are translated to
uppercase, unless they are escaped with a single '=' character prefix.

There is some upheaval about the reliability of DNS for this sort of
lookup; midget and midput will mostly be used on locally hosted domains,
and if not then it is nowadays a good practice to use DNSSEC to overcome
such problems.

Given DNS confirmation, the derived domain name is queried for an IMAP
server as declared in SRV records. This server is then approached,
Kerberos-based authentication is performed. During authentication, a
login name is sent to the IMAP server. For `user/detail@REALM` names,
this will be detail; for `user@REALM` names, this will be user. For any
other forms (if they exist at all), this will be the local account name
under which you are logged in.

**TODO:** For now, you need to manually configure the IMAP server name
in the midget and midput scripts. They are set in the variable
remote\_hostname.

## Where do the filenames come from?

Each of the retrieved files is stored in the filesystem. The tool will
create a file named after the `Message-` or `Content-ID`; if it already
exists it will fail and complain; you probably downloaded the same
content twice, and if not then this may be a sign that the sender is
trying to overwrite local files on your system, which is a warning sign.
If a filename is found in the descriptive information sent along the
attachmant, then midget will try to create a link with that filename as
well; this will fail with a non-fatal warning if the filename exists.

Note that the unique value of the `Message-` or `Content-ID` is the
reason to not be cautious when writing a file by that name. It would be
incredibly unlikely that you had a file on your system with the same
name. And yes, some thought is necessary to avoid local files
overwritten by submitted devious content. So perhaps it is better to
raise a fatal error if the name already exists?

## Desktop tool support

Mailers may hide the `mid:` and `cid:` URIs from you, the silly mouse
operator. It would be advised to use these URIs as copy/paste format, as
well as what gets pasted into a shell when an attechment is dragged into
it.

Maybe this will be a battle, maybe not. As so often, the commandline is
leading the way forward, and welcoming the GUI to follow suit ;-)

It is certainly useful to be able to use `mid:` and `cid:` references in
chat sessions, to refer back to a previously exchanged email attachment.

## Generating these URIs

If you are building a tool that handles email messages, you should
consider offering a clickable `mid:` URI to access the message body and
any attachments.

Operating systems and browsers generally support new URI schemes with a
registry, and applications can be setup to register against those. It is
easily imaginable that desktop versions of midget are created to handle
such downloads.

Another advantage of visible `mid:` URIs is that they can be copy/pasted
or dragged into shells, chat sessions, and so on. This makes them usable
to crossover to remote locations, where the files can then be used. You
may not want to offer this is the only option, but it certainly is a
useful option to offer to end users.

You should not generate `cid:` URIs if you can avoid it. The `mid:`
format includes the `Message-ID`, and that is a bit more work but it
saves a lot of search time when downloading it. This is due to the IMAP
protocol, which has special constructs for matches with header names
such as the `Message-ID`, but not for MIME-headers such as `Content-ID`.
The latter must therefore be resolved with full-text search, and that is
not open to optimisations like the `Message-ID` is.

Read [RFC 2392][] for details; but in short, you will be removing
angular brackets and applying percent-escaping to the remainder. Be sure
to also escape any slash that occurs in the string. If you are setting
up a `mid:` for a message body, then this is all; for an attachment, the
same procedure should be applied to the `Content-ID` header and it
should be attached with a separating slash.

Finally, application environments (so, operating systems and browsers)
usually are capable of doing something useful with a MIME-type. This is
indeed taken into account.

  [RFC 2392]: https://tools.ietf.org/html/rfc2392
