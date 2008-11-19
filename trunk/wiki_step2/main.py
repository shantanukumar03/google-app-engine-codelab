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

"""Main application file for Wiki example.

Includes:
BaseRequestHandler
MainHandler
ViewHandler
EditHandler
SaveHandler
"""

__author__ = 'appengine-support@google.com'

# Python Imports
import os
import sys
import re
import urllib
import wsgiref.handlers
import xml.dom.minidom

# Google App Engine Imports
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
      wiki_user = WikiUser.gql('WHERE wiki_user = :1', user).get()
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



_WIKI_URLS = [('/', MainHandler),
              ('/view/([^/]+)', ViewHandler),
              ('/edit/([^/]+)', EditHandler),
              ('/save/([^/]+)', SaveHandler)]

def main():
  application = webapp.WSGIApplication(_WIKI_URLS, debug=_DEBUG)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
  main()