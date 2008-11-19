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
"""

# Python Imports
import os
import sys
import re
import wsgiref.handlers

# Google App Engine Imports
from google.appengine.ext import webapp
from google.appengine.api import users
from google.appengine.ext.webapp import template

# Wiki Imports
from markdown import markdown
from wiki_model import WikiPage


_DEBUG = True
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
    user = users.get_current_user()
    
    if user:
      log_in_out_url = users.create_logout_url('/view/StartPage')
    else:
      log_in_out_url = users.create_login_url(self.request.path)
    
    values = {'user': user, 'log_in_out_url': log_in_out_url}
    values.update(template_values)
    directory = os.path.dirname(__file__)
    path = os.path.join(directory, 'templates', template_name)
    self.response.out.write(template.render(path, values, debug=_DEBUG))


class MainHandler(BaseRequestHandler):
  """The MainHandler extends the base request handler, and handles all
     requests to the url http://wikiapp.appspot.com/
  """

  def get(self):
    """When we request the base page, we direct users to the StartPage
    """
    self.redirect('view/StartPage')
    
    
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
    # Attempt to locate the page
    entry = WikiPage.gql('WHERE title = :1', page_title).get()
    
    # If it exists, render the body, if not, don't
    if entry and entry.body:
        wiki_body, count = _WIKI_WORD.subn(r'<a href="/view/\1" >\1</a>', entry.body)
        wiki_body = markdown.markdown(wiki_body)
        author = entry.author
    else:
        wiki_body = ""
        author = ""
    
    self.generate('view.html', template_values={'page_title': page_title,
                                                'body': wiki_body,
                                                'author': author})


class EditHandler(BaseRequestHandler):
  """When we receive an HTTP Get request to edit pages, we pull that
     page from the datastore and allow the user to edit.  If the page does 
     not exist we pass empty arguments to the template and the template 
     allows the user to create the page
  """
  
  def get(self, page_title):
    # A user must be signed in to edit the page    
    current_user = users.get_current_user()
    
    if not current_user:
      self.redirect(users.create_login_url(self.request.path))
      
    # Display the existing body if it exists
    entry = WikiPage.gql('WHERE title = :1', page_title).get()
    
    self.generate('edit.html', template_values={'page_title': page_title,
                                                'entry': entry})


class SaveHandler(BaseRequestHandler):
  """From the edit page for a wiki article, we post to the SaveHandler
     This creates the the entry and revision for the datastore
  """
  
  def post(self, page_title):

    current_user = users.get_current_user()
    
    if not current_user:
      self.redirect(users.create_login_url("/edit/" + page_title))

    # Get the posted edit
    body = self.request.get('body')
    
    # If the entry exists, overwrite it, if not, create it
    entry = WikiPage.gql('WHERE title = :1', page_title).get()
    
    if entry:
        entry.body = body
        entry.author = current_user
    else:
        entry = WikiPage(title=page_title, body=body, author=current_user)

    entry.put()
    self.redirect('/view/' + page_title)


def main():
  application = webapp.WSGIApplication([('/', MainHandler),
                                       ('/view/([^/]+)', ViewHandler),
                                       ('/edit/([^/]+)', EditHandler),
                                       ('/save/([^/]+)', SaveHandler)],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
