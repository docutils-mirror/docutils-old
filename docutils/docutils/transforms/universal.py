# Authors: David Goodger, Ueli Schlaepfer
# Contact: goodger@users.sourceforge.net
# Revision: $Revision$
# Date: $Date$
# Copyright: This module has been placed in the public domain.

"""
Transforms needed by most or all documents:

- `Decorations`: Generate a document's header & footer.
- `Messages`: Placement of system messages stored in
  `nodes.document.transform_messages`.
- `TestMessages`: Like `Messages`, used on test runs.
- `FinalReferences`: Resolve remaining references.
"""

__docformat__ = 'reStructuredText'

import re
import sys
import time
from docutils import nodes, utils
from docutils.transforms import TransformError, Transform


class Decorations(Transform):

    """
    Populate a document's decoration element (header, footer).
    """

    default_priority = 820

    def apply(self):
        header = self.generate_header()
        footer = self.generate_footer()
        if header or footer:
            decoration = nodes.decoration()
            decoration += header
            decoration += footer
            document = self.document
            index = document.first_child_not_matching_class(
                nodes.PreDecorative)
            if index is None:
                document += decoration
            else:
                document[index:index] = [decoration]

    def generate_header(self):
        return None

    def generate_footer(self):
        # @@@ Text is hard-coded for now.
        # Should be made dynamic (language-dependent).
        settings = self.document.settings
        if settings.generator or settings.datestamp or settings.source_link \
               or settings.source_url:
            text = []
            if settings.source_link and settings._source \
                   or settings.source_url:
                if settings.source_url:
                    source = settings.source_url
                else:
                    source = utils.relative_path(settings._destination,
                                                 settings._source)
                text.extend([
                    nodes.reference('', 'View document source',
                                    refuri=source),
                    nodes.Text('.\n')])
            if settings.datestamp:
                datestamp = time.strftime(settings.datestamp, time.gmtime())
                text.append(nodes.Text('Generated on: ' + datestamp + '.\n'))
            if settings.generator:
                text.extend([
                    nodes.Text('Generated by '),
                    nodes.reference('', 'Docutils', refuri=
                                    'http://docutils.sourceforge.net/'),
                    nodes.Text(' from '),
                    nodes.reference('', 'reStructuredText', refuri='http://'
                                    'docutils.sourceforge.net/rst.html'),
                    nodes.Text(' source.\n')])
            footer = nodes.footer()
            footer += nodes.paragraph('', '', *text)
            return footer
        else:
            return None


class Messages(Transform):

    """
    Place any system messages generated after parsing into a dedicated section
    of the document.
    """

    default_priority = 860

    def apply(self):
        unfiltered = self.document.transform_messages
        threshold = self.document.reporter['writer'].report_level
        messages = []
        for msg in unfiltered:
            if msg['level'] >= threshold and not msg.parent:
                messages.append(msg)
        if messages:
            section = nodes.section(classes=['system-messages'])
            # @@@ get this from the language module?
            section += nodes.title('', 'Docutils System Messages')
            section += messages
            self.document.transform_messages[:] = []
            self.document += section


class FilterMessages(Transform):

    """
    Remove system messages below verbosity threshold.
    """

    default_priority = 870

    def apply(self):
        visitor = SystemMessageFilterVisitor(self.document)
        self.document.walk(visitor)


class SystemMessageFilterVisitor(nodes.SparseNodeVisitor):

    def unknown_visit(self, node):
        pass

    def visit_system_message(self, node):
        if node['level'] < self.document.reporter['writer'].report_level:
            node.parent.remove(node)


class TestMessages(Transform):

    """
    Append all post-parse system messages to the end of the document.
    """

    default_priority = 890

    def apply(self):
        for msg in self.document.transform_messages:
            if not msg.parent:
                self.document += msg


class FinalChecks(Transform):

    """
    Perform last-minute checks and transforms.

    - Check for dangling references (incl. footnote & citation).
    - Check for illegal transitions, move transitions.
    """

    default_priority = 840

    def apply(self):
        visitor = FinalCheckVisitor(
            self.document,
            self.document.transformer.unknown_reference_resolvers)
        self.document.walk(visitor)
        if self.document.settings.expose_internals:
            visitor = InternalAttributeExposer(self.document)
            self.document.walk(visitor)
        # *After* resolving all references, check for unreferenced
        # targets:
        for target in self.document.traverse():
            if isinstance(target, nodes.target) and not target.referenced:
                if target['names']:
                    naming = target['names'][0]
                elif target['ids']:
                    naming = target['ids'][0]
                else:
                    # Hack: Propagated targets always have their refid
                    # attribute set.
                    naming = target['refid']
                self.document.reporter.info(
                    'Hyperlink target "%s" is not referenced.'
                    % naming, base_node=target)


class FinalCheckVisitor(nodes.SparseNodeVisitor):
    
    def __init__(self, document, unknown_reference_resolvers):
        nodes.SparseNodeVisitor.__init__(self, document)
        self.document = document
        self.unknown_reference_resolvers = unknown_reference_resolvers

    def unknown_visit(self, node):
        pass

    def visit_reference(self, node):
        if node.resolved or not node.hasattr('refname'):
            return
        refname = node['refname']
        id = self.document.nameids.get(refname)
        if id is None:
            for resolver_function in self.unknown_reference_resolvers:
                if resolver_function(node):
                    break
            else:
                if self.document.nameids.has_key(refname):
                    msg = self.document.reporter.error(
                        'Duplicate target name, cannot be used as a unique '
                        'reference: "%s".' % (node['refname']), base_node=node)
                else:
                    msg = self.document.reporter.error(
                        'Unknown target name: "%s".' % (node['refname']),
                        base_node=node)
                msgid = self.document.set_id(msg)
                prb = nodes.problematic(
                      node.rawsource, node.rawsource, refid=msgid)
                prbid = self.document.set_id(prb)
                msg.add_backref(prbid)
                node.parent.replace(node, prb)
        else:
            del node['refname']
            node['refid'] = id
            self.document.ids[id].note_referenced_by(id=id)
            node.resolved = 1

    visit_footnote_reference = visit_citation_reference = visit_reference

    def visit_transition(self, node):
        """
        Move transitions at the end of sections up the tree.  Complain
        on transitions after a title, at the beginning or end of the
        document, and after another transition.

        For example, transform this::

            <section>
                ...
                <transition>
            <section>
                ...

        into this::

            <section>
                ...
            <transition>
            <section>
                ...
        """
        index = node.parent.index(node)
        error = None
        if (index == 0 or
            isinstance(node.parent[0], nodes.title) and
            (index == 1 or
             isinstance(node.parent[1], nodes.subtitle) and
             index == 2)):
            assert (isinstance(node.parent, nodes.document) or
                    isinstance(node.parent, nodes.section))
            error = self.document.reporter.error(
                'Document or section may not begin with a transition.',
                line=node.line)
        elif isinstance(node.parent[index - 1], nodes.transition):
            error = self.document.reporter.error(
                'At least one body element must separate transitions; '
                'adjacent transitions are not allowed.', line=node.line)
        if error:
            # Insert before node and update index.
            node.parent.insert(index, error)
            index += 1
        assert index < len(node.parent)
        if index != len(node.parent) - 1:
            # No need to move the node.
            return
        # Node behind which the transition is to be moved.
        sibling = node
        # While sibling is the last node of its parent.
        while index == len(sibling.parent) - 1:
            sibling = sibling.parent
            # If sibling is the whole document (i.e. it has no parent).
            if sibling.parent is None:
                # Transition at the end of document.  Do not move the
                # transition up, and place an error behind.
                error = self.document.reporter.error(
                    'Document may not end with a transition.',
                    line=node.line)
                node.parent.insert(node.parent.index(node) + 1, error)
                return
            index = sibling.parent.index(sibling)
        # Remove the original transition node.
        node.parent.remove(node)
        # Insert the transition after the sibling.
        sibling.parent.insert(index + 1, node)


class InternalAttributeExposer(nodes.GenericNodeVisitor):

    def __init__(self, document):
        nodes.GenericNodeVisitor.__init__(self, document)
        self.internal_attributes = document.settings.expose_internals

    def default_visit(self, node):
        for att in self.internal_attributes:
            value = getattr(node, att, None)
            if value is not None:
                node['internal:' + att] = value
