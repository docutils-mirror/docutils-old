# .. coding: utf8
# :Author: Günter Milde <milde@users.berlios.de>
# :Revision: $Revision$
# :Date: $Date: 2005-06-28$
# :Copyright: © 2005, 2009 Günter Milde.
#             Released  without warranties or conditions of any kind
#             under the terms of the Apache License, Version 2.0
# 	      http://www.apache.org/licenses/LICENSE-2.0

"""
Strict HyperText Markup Language document tree Writer.

This is a variant of Docutils' standard 'html4css1' writer.

TODO: ensure the follwing is true for all output:
 * The output conforms to the XHTML version 1.0 Strict DTD.
 * It contains no hard-coded formatting information that would prevent
   layout design by cascading style sheets.
"""

__docformat__ = 'reStructuredText'

import os
import os.path
import re

import docutils
from docutils import frontend, nodes, utils, writers, languages
from docutils.writers import html4css1

class Writer(html4css1.Writer):

    supported = ('html', 'xhtml',
                 'html4strict', 'xhtml1strict',
                 'html4css2', 'xhtml1css2')
    """Formats this writer supports."""

    default_stylesheets = ['html4css1.css', 'html4css2.css']

    default_stylesheet_path = ','.join(
        [os.path.join(os.path.dirname(__file__), stylesheet)
         for stylesheet in default_stylesheets])

    default_template_path = html4css1.Writer.default_template_path

    config_section = 'html4strict writer'

    settings_spec = frontend.filter_settings_spec(
        html4css1.Writer.settings_spec,
        'field_name_limit',
        stylesheet_path = (
            'Specify comma separated list of stylesheet paths. '
	    'With --link-stylesheet, '
            'the path is rewritten relative to the output HTML file. '
            'Default: "%s"' % default_stylesheet_path,
            ['--stylesheet-path'],
            {'metavar': '<file>', 'overrides': 'stylesheet',
            'default': default_stylesheet_path}))

    def __init__(self):
        writers.Writer.__init__(self)
        self.translator_class = HTMLTranslator


class HTMLTranslator(html4css1.HTMLTranslator):
    """
    This writer generates XHTML 1.0 Strict
    without formatting hints that interfere with a CSS stylesheet.
    """
    doctype = ('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" '
               '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n')

    # TODO: References (citations) as list instead of table

    # tag citation references with <cite>

    def visit_citation_reference(self, node):
        href = '#' + node['refid']
        self.body.append('<cite>')
        self.body.append(self.starttag(
            node, 'a', '[', CLASS='citation-reference', href=href))

    def depart_citation_reference(self, node):
        self.body.append(']</a></cite>')

    # enumerated lists
    # ----------------
    #
    # The 'start' attribute does not conform to HTML4/XHTML1 Strict
    # (it will resurface in HTML5)
    def visit_enumerated_list(self, node):
        atts = {}
        if 'start' in node:
            atts['style'] = 'counter-reset: item %d;' % (node['start'] - 1)
        if 'enumtype' in node:
            atts['class'] = node['enumtype']
        # @@@ To do: prefix, suffix.
        old_compact_simple = self.compact_simple
        self.context.append((self.compact_simple, self.compact_p))
        self.compact_p = None
        self.compact_simple = self.is_compactable(node)
        if self.compact_simple and not old_compact_simple:
            atts['class'] = (atts.get('class', '') + ' simple').strip()
        self.body.append(self.starttag(node, 'ol', **atts))

    # field-list as definition list, styled with CSS
    # ----------------------------------------------

    def visit_field_list(self, node):
        self.body.append(
            self.starttag(node, 'dl', CLASS='docutils field-list'))

    def depart_field_list(self, node):
        self.body.append('</dl>\n')

    def visit_field(self, node):
        pass

    def depart_field(self, node):
        pass

    def visit_field_name(self, node):
        self.body.append(self.starttag(node, 'dt', '', CLASS='field-name'))

    def depart_field_name(self, node):
        self.body.append('</dt>\n')

    def visit_field_body(self, node):
        self.body.append(self.starttag(node, 'dd', '', CLASS='field-body'))
        self.set_class_on_child(node, 'first', 0)
        field = node.parent
        if (self.compact_field_list or
            isinstance(field.parent, nodes.docinfo) or
            field.parent.index(field) == len(field.parent) - 1):
            # If we are in a compact list, the docinfo, or if this is
            # the last field of the field list, do not add vertical
            # space after last element.
            self.set_class_on_child(node, 'last', -1)

    def depart_field_body(self, node):
        self.body.append('</dd>\n')

    # docinfo list also a definition list
    # -----------------------------------

    def visit_docinfo(self, node):
        self.body.append(
            self.starttag(node, 'dl', CLASS='docutils docinfo'))

    def depart_docinfo(self, node):
        self.body.append('</dl>\n')

    def visit_docinfo_item(self, node, name, meta=1):
        if meta:
            meta_tag = '<meta name="%s" content="%s" />\n' \
                       % (name, self.attval(node.astext()))
            self.add_meta(meta_tag)
        self.body.append('<dt class="field-name docinfo">%s</dt>\n'
                         % self.language.labels[name])
        self.body.append(self.starttag(node, 'dd', '', CLASS='field-body docinfo'))
        if len(node):
            if isinstance(node[0], nodes.Element):
                node[0]['classes'].append('first')
            if isinstance(node[-1], nodes.Element):
                node[-1]['classes'].append('last')

    def depart_docinfo_item(self):
        self.body.append('</dd>\n')

    # Attribute "align" cannot be used for <img> and <div> element
    # ---------------------------------------------------------------

    # TODO: could the "align" attribute be stripped also in html4css1?
    def visit_image(self, node):
        atts = {}
        atts['src'] = node['uri']
        if 'width' in node:
            atts['width'] = node['width']
        if 'height' in node:
            atts['height'] = node['height']
        if 'scale' in node:
            if Image and not ('width' in node
                              and 'height' in node):
                try:
                    im = Image.open(str(atts['src']))
                except (IOError, # Source image can't be found or opened
                        UnicodeError):  # PIL doesn't like Unicode paths.
                    pass
                else:
                    if 'width' not in atts:
                        atts['width'] = str(im.size[0])
                    if 'height' not in atts:
                        atts['height'] = str(im.size[1])
                    del im
            for att_name in 'width', 'height':
                if att_name in atts:
                    match = re.match(r'([0-9.]+)(\S*)$', atts[att_name])
                    assert match
                    atts[att_name] = '%s%s' % (
                        float(match.group(1)) * (float(node['scale']) / 100),
                        match.group(2))
        style = []
        for att_name in 'width', 'height':
            if att_name in atts:
                if re.match(r'^[0-9.]+$', atts[att_name]):
                    # Interpret unitless values as pixels.
                    atts[att_name] += 'px'
                style.append('%s: %s;' % (att_name, atts[att_name]))
                del atts[att_name]
        if style:
            atts['style'] = ' '.join(style)
        atts['alt'] = node.get('alt', atts['src'])
        if (isinstance(node.parent, nodes.TextElement) or
            (isinstance(node.parent, nodes.reference) and
             not isinstance(node.parent.parent, nodes.TextElement))):
            # Inline context or surrounded by <a>...</a>.
            suffix = ''
        else:
            suffix = '\n'
        if 'align' in node:
            atts['class'] = 'align-%s' % node['align']
        self.context.append('')
        self.body.append(self.emptytag(node, 'img', suffix, **atts))


    # Literal role pre-formatted
    # --------------------------

    # Setting tt.literal to {white-space: pre} (in the style sheet)  will
    # protect text like "--an-option" or the regular expression
    # ``[+]?(\d+(\.\d*)?|\.\d+)`` from bad line wrapping and protect runs of
    # multiple spaces but allow clean HTML code (see bug #1938891)
    # This way, the wrapping can be configured in a custom style.

    def visit_literal(self, node):
        self.body.append(
            self.starttag(node, 'tt', '', CLASS='docutils literal'))

    def depart_literal(self, node):
        self.body.append('</tt>')

    # no hard-coded border setting in the table head
    # ----------------------------------------------

    def visit_table(self, node):
        self.body.append(
            self.starttag(node, 'table', CLASS='docutils table'))