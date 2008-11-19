#!/usr/bin/env python
#
# Copyright 2008 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

__author__ = 'appengine-support@google.com'

"""Main application file for Wiki example.

Includes:
BaseRequestHandler - Base class to handle requests
MainHandler - Handles request to TLD
ViewHandler - Handles request to view any wiki entry
EditHandler - Handles request to edit any wiki entry
SaveHandler - Handles request to save any wiki entry
UserProfileHandler - Handles request to view any user profile
EditUserProfileHandler - Handles request to edit current user profile
GetUserPhotoHandler - Serves a users image
SendAdminEmail - Handles request to send the admins email
"""

__author__ = 'appengine-support@google.com'

# Python Imports
import os
import sys
import re
import urllib
import wsgiref.handlers
import xml.dom.minidom
import logging

# Google App Engine Imports
from google.appengine.api import images
from google.appengine.api import mail
from google.appengine.api import users
from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

# Wiki Imports
from markdown import markdown
from wiki_model import WikiContent
from wiki_model import WikiRevision
from wiki_model import WikiUser

# Set the debug level
_DEBUG = True

_ADMIN_EMAIL='hackathon.rsvp@gmail.com'
# Regular expression for a wiki word.  Wiki words are all letters
# As well as camel case.  For example: WikiWord
_WIKI_WORD = re.compile('\\b([A-Z][a-z]+[A-Z][A-Za-z]+)\\b')

class BaseRequestHandler(webapp.RequestHandler):
  """Base request handler extends webapp.Request handler

     It defines the generate method, which renders a Django template
     in response to a web request
  """

  def generate(self, template_name, template_values={}):
    """Generate takes renders and HTML template along with values
       passed to that template

       Args:
         template_name: A string that represents the name of the HTML template
         template_values: A dictionary that associates objects with a string
           assigned to that object to call in the HTML template.  The defualt
           is an empty dictionary.
    """
    # We check if there is a current user and generate a login or logout URL
    user = users.get_current_user()

    if user:
      log_in_out_url = users.create_logout_url('/view/StartPage')
    else:
      log_in_out_url = users.create_login_url(self.request.path)

    # We'll display the user name if available and the URL on all pages
    values = {'user': user, 'log_in_out_url': log_in_out_url}
    values.update(template_values)

    # Construct the path to the template
    directory = os.path.dirname(__file__)
    path = os.path.join(directory, 'templates', template_name)

    # Respond to the request by rendering the template
    self.response.out.write(template.render(path, values, debug=_DEBUG))

class MainHandler(BaseRequestHandler):
  """The MainHandler extends the base request handler, and handles all
     requests to the url http://wikiapp.appspot.com/
  """

  def get(self):
    """When we request the base page, we direct users to the StartPage
    """
    self.redirect('/view/StartPage')


class ViewHandler(BaseRequestHandler):
  """This class defines the request handler that handles all requests to the
     URL http://wikiapp.appspot.com/view/*
  """

  def get(self, page_title):
    """When we receive an HTTP Get request to the view pages, we pull that
       page from the datastore and render it.  If the page does not exist
       we pass empty arguments to the template and the template displays
       the option to the user to create the page
    """
    # Find the wiki entry
    entry = WikiContent.gql('WHERE title = :1', page_title).get()

    if entry:
      # Retrieve the current version
      current_version = WikiRevision.gql('WHERE wiki_page =  :1 '
                                         'ORDER BY version_number DESC', entry).get()
      # Define the body, version number, author email, author nickname
      # and revision date
      body = current_version.revision_body
      version = current_version.version_number
      author_email = urllib.quote(current_version.author.wiki_user.email())
      author_nickname = current_version.author.wiki_user.nickname()
      version_date = current_version.created
      # Replace all wiki words with links to those wiki pages
      wiki_body, count = _WIKI_WORD.subn(r'<a href="/view/\1">\1</a>',
                                         body)
      # Markdown the body to allow formatting of the wiki page
      wiki_body = markdown.markdown(wiki_body)

    else:
      # These things do not exist
      wiki_body = ''
      author_email = ''
      author_nickname = ''
      version = ''
      version_date = ''

    # Render the template view.html, which extends base.html
    self.generate('view.html', template_values={'page_title': page_title,
                                                'body': wiki_body,
                                                'author': author_nickname,
                                                'author_email': author_email,
                                                'version': version,
                                                'version_date': version_date})


class EditHandler(BaseRequestHandler):
  """When we receive an HTTP Get request to edit pages, we pull that
     page from the datastore and allow the user to edit.  If the page does 
     not exist we pass empty arguments to the template and the template 
     allows the user to create the page
  """
  def get(self, page_title):
    # We require that the user be signed in to edit a page
    current_user = users.get_current_user()

    if not current_user:
      self.redirect(users.create_login_url('/edit/' + page_title))

    # Get the entry along with the current version
    entry = WikiContent.gql('WHERE title = :1', page_title).get()

    current_version = WikiRevision.gql('WHERE wiki_page = :1 '
                                       'ORDER BY version_number DESC', entry).get()

    # Generate edit template, which posts to the save handler
    self.generate('edit.html',
                  template_values={'page_title': page_title,
                                   'current_version': current_version})


class SaveHandler(BaseRequestHandler):
  """From the edit page for a wiki article, we post to the SaveHandler
     This creates the the entry and revision for the datastore
  """

  def post(self, page_title):
    # Again, only accept saves from a signed in user
    current_user = users.get_current_user()

    if not current_user:
      self.redirect(users.create_login_url('/edit/' + page_title))

    # See if this user has a profile
    wiki_user = WikiUser.gql('WHERE wiki_user = :1', current_user).get()

    # If not, create the profile
    if not wiki_user:
      wiki_user = WikiUser(wiki_user=current_user)
      wiki_user.put()

    # get the user entered content in the form
    body = self.request.get('body')

    # Find the entry, if it exists
    entry = WikiContent.gql('WHERE title = :1', page_title).get()

    # Generate the version number based on the entries previous existence
    if entry:
      latest_version = WikiRevision.gql('WHERE wiki_page = :content'
                                        ' ORDER BY version_number DESC', content=entry).get()
      version_number = latest_version.version_number + 1
    else:
      version_number = 1
      entry = WikiContent(title=page_title)
      entry.put()

    # Create a version for this entry
    version = WikiRevision(version_number=version_number,
                           revision_body=body, author=wiki_user,
                           wiki_page=entry)
    version.put()

    # After the entry has been saved, direct the user back to view the page
    self.redirect('/view/' + page_title)


class UserProfileHandler(BaseRequestHandler):
  """Allows a user to view another user's profile.  All users are able to
     view this information by requesting http://wikiapp.appspot.com/user/*
  """

  def get(self, user):
    """When requesting the URL, we find out that user's WikiUser information.
       We also retrieve articles written by the user
    """
    # Webob over quotes the request URI, so we have to unquote twice
    unescaped_user = urllib.unquote(urllib.unquote(user))

    # Query for the user information
    wiki_user_object = users.User(unescaped_user)
    wiki_user = WikiUser.gql('WHERE wiki_user = :1', wiki_user_object).get()

    # Retrieve the unique set of articles the user has revised
    # Please note that this doesn't gaurentee that user's revision is
    # live on the wiki page
    article_list = []
    for article in wiki_user.wikirevision_set:
      article_list.append(article.wiki_page.title)
    articles = set(article_list)

    # If the user has specified a feed, fetch it
    feed_content = ''
    feed_titles = []
    if wiki_user.user_feed:
      feed = urlfetch.fetch(wiki_user.user_feed)
      # If the fetch is a success, get the blog article titles
      if feed.status_code == 200:
        feed_content = feed.content
        xml_content = xml.dom.minidom.parseString(feed_content)
        for title in xml_content.getElementsByTagName('title'):
          feed_titles.append(title.childNodes[0].nodeValue)
    # Generate the user profile
    self.generate('user.html', template_values={'queried_user': wiki_user,
                                                'articles': articles,
                                                'titles': feed_titles})

class EditUserProfileHandler(BaseRequestHandler):
  """This allows a user to edit his or her wiki profile.  The user can upload
     a picture and set a feed URL for personal data
  """
  def get(self, user):
    # Get the user information
    unescaped_user = urllib.unquote(user)
    wiki_user_object = users.User(unescaped_user)
    # Only that user can edit his or her profile
    if users.get_current_user() != wiki_user_object:
      self.redirect('/view/StartPage')

    wiki_user = WikiUser.gql('WHERE wiki_user = :1', wiki_user_object).get()
    if not wiki_user:
      wiki_user = WikiUser(wiki_user=wiki_user_object)
      wiki_user.put()

    article_list = []
    for article in wiki_user.wikirevision_set:
      article_list.append(article.wiki_page.title)
    articles = set(article_list)
    self.generate('edit_user.html', template_values={'queried_user': wiki_user,
                                                     'articles': articles})

  def post(self, user):
    # Get the user information
    unescaped_user = urllib.unquote(user)
    wiki_user_object = users.User(unescaped_user)
    # Only that user can edit his or her profile
    if users.get_current_user() != wiki_user_object:
      self.redirect('/view/StartPage')

    wiki_user = WikiUser.gql('WHERE wiki_user = :1', wiki_user_object).get()

    user_photo = self.request.get('user_picture')
    if user_photo:
      raw_photo = images.Image(user_photo)
      raw_photo.resize(width=256, height=256)
      raw_photo.im_feeling_lucky()
      wiki_user.wiki_user_picture = raw_photo.execute_transforms(output_encoding=images.PNG)
    feed_url = self.request.get('feed_url')
    if feed_url:
      wiki_user.user_feed = feed_url

    wiki_user.put()


    self.redirect('/user/%s' % user)


class GetUserPhotoHandler(BaseRequestHandler):
  """This is a class that handles serving the image for a user
     
     The template requests /getphoto/example@test.com and the handler
     retrieves the photo from the datastore, sents the content-type
     and returns the photo
  """

  def get(self, user):
    unescaped_user = urllib.unquote(user)
    wiki_user_object = users.User(unescaped_user)
    # Only that user can edit his or her profile
    if users.get_current_user() != wiki_user_object:
      self.redirect('/view/StartPage')

    wiki_user = WikiUser.gql('WHERE wiki_user = :1', wiki_user_object).get()
    
    if wiki_user.wiki_user_picture:
      self.response.headers['Content-Type'] = 'image/jpg'
      self.response.out.write(wiki_user.wiki_user_picture)


class SendAdminEmail(BaseRequestHandler):
  """Sends the admin email.

     The user must be signed in to send email to the admins
  """
  def get(self):
    # Check to see if the user is signed in
    current_user = users.get_current_user()

    if not current_user:
      self.redirect(users.create_login_url('/sendadminemail'))

    # Generate the email form
    self.generate('admin_email.html')

  def post(self):
    # Check to see if the user is signed in
    current_user = users.get_current_user()

    if not current_user:
      self.redirect(users.create_login_url('/sendadminemail'))

    # Get the email subject and body
    subject = self.request.get('subject')
    body = self.request.get('body')

    # send the email
    mail.send_mail_to_admins(sender=current_user.email(), reply_to=current_user.email(),
                             subject=subject, body=body)

    # Generate the confirmation template
    self.generate('confirm_email.html')

_WIKI_URLS = [('/', MainHandler),
              ('/view/([^/]+)', ViewHandler),
              ('/edit/([^/]+)', EditHandler),
              ('/save/([^/]+)', SaveHandler),
              ('/user/([^/]+)', UserProfileHandler),
              ('/edituser/([^/]+)', EditUserProfileHandler),
              ('/getphoto/([^/]+)', GetUserPhotoHandler),
              ('/sendadminemail', SendAdminEmail)]

def main():
  application = webapp.WSGIApplication(_WIKI_URLS, debug=_DEBUG)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
  main()