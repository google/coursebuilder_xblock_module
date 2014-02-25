# Copyright 2014 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Integration tests for the XBlock module and core XBlocks."""

__author__ = 'jorr@google.com (John Orr)'

import os
import time

from selenium.webdriver.support import wait
from tests.integration import test_classes


class BaseDomObject(object):
    """Base object to provide object model for a DOM element."""

    def __init__(self, root):
        self.root = root

    def _element(self, css_selector):
        return self.root.find_element_by_css_selector(css_selector)

    def _elements(self, css_selector):
        return self.root.find_elements_by_css_selector(css_selector)


class Sequence(BaseDomObject):
    """Provide object model for manipulating the Sequence XBlock."""

    def click_item(self, item):
        nav_buttons = self._elements('ul.sequence_nav li.nav_button > a')
        nav_buttons[item].click()

    def click_next(self):
        self._element('ul.sequence_nav li.next > a').click()

    def click_prev(self):
        self._element('ul.sequence_nav li.prev > a').click()

    def assert_selected(self, index):
        children = self._elements('div.content > div')
        for i, child in enumerate(children):
            assert (
                i == index and not child.get_attribute('class')) or (
                i != index and child.get_attribute('class') == 'hidden')

    def get_child(self, index):
        return self._elements('div.content > div > div.xblock')[index]


class Vertical(BaseDomObject):
    """Provide object model for manipulating a Vertical XBlock."""

    def get_child(self, index):
        return self._elements('div.vertical > div > div.xblock')[index]


class MultipleChoiceProblem(BaseDomObject):
    """Provide object model for manipulating a Capa Multiple Choice XBlock."""

    def get_choices(self):
        return [
            MultipleChoiceItem(item)
            for item in self._elements('fieldset > label')]

    def click_choice(self, index):
        self.get_choices()[index].click()

    def click_check(self):
        self._element('section.action input.check').click()
        time.sleep(1)

    def assert_choice_text(self, choice_text):
        assert choice_text == [
            choice.get_text() for choice in self.get_choices()]

    def assert_graded_incorrect(self, index):
        for i, choice in enumerate(self.get_choices()):
            assert (
                i == index and choice.is_incorrect()) or (
                i != index and choice.is_neither())

    def assert_graded_correct(self, index):
        for i, choice in enumerate(self.get_choices()):
            assert (
                i == index and choice.is_correct()) or (
                i != index and choice.is_neither())

    def assert_show_answers_hidden(self):
        assert not self._elements('section.action button.show')

    def assert_show_answers_visible(self):
        assert self._elements('section.action button.show')


class MultipleChoiceItem(BaseDomObject):

    def get_text(self):
        return self.root.text

    def click(self):
        self._element('input[type=radio]').click()

    def is_correct(self):
        return self.root.get_attribute('class') == 'choicegroup_correct'

    def is_incorrect(self):
        return self.root.get_attribute('class') == 'choicegroup_incorrect'

    def is_neither(self):
        return not self.root.get_attribute('class')


class MultipleSelectionProblem(BaseDomObject):
    """Provide object model for manipulating a Multiple Choice (checkbox)."""

    def get_question_text(self):
        return self._element('section.problem > div > p').text

    def select(self, index_list):
        selected_checkboxes = self._elements(
            'section.problem input:checked[type=checkbox]')
        for checkbox in selected_checkboxes:
            checkbox.click()

        checkboxes = self._elements('section.problem input[type=checkbox]')
        for index in index_list:
            checkboxes[index].click()

    def click_check(self):
        self._element('section.action input.check').click()
        time.sleep(1)

    def assert_graded_correct(self):
        assert self._elements('div.indicator_container > span.correct')

    def assert_graded_incorrect(self):
        assert self._elements('div.indicator_container > span.incorrect')

    def assert_selected(self, index_list):
        checkboxes = self._elements('section.problem input[type=checkbox]')
        for i, checkbox in enumerate(checkboxes):
            assert (
                i in index_list and checkbox.is_selected()) or (
                i not in index_list and not checkbox.is_selected())


class CourseBuilderXBlockTests(test_classes.BaseIntegrationTest):

    def upload_archive(self, course_name, filename):
        archive_file = os.path.join(
            os.path.dirname(__file__), 'resources', filename)
        archive_file = os.path.abspath(archive_file)

        self.driver.get('%s/%s/dashboard?action=import_xblock' % (
            self.INTEGRATION_SERVER_BASE_URL, course_name))

        wait.WebDriverWait(self.driver, 15).until(
            lambda d: d.find_element_by_link_text('Import'))
        self.driver.find_element_by_name('file').send_keys(archive_file)
        self.driver.find_element_by_link_text('Import').click()

        def upload_successfully_imported(d):
            msg_div = d.find_element_by_css_selector(
                '#formContainer > div.cb-oeditor-xblock-import-msg')
            return msg_div and msg_div.text.startswith(
                'Upload successfully imported:')
        wait.WebDriverWait(self.driver, 15).until(upload_successfully_imported)

    def load_unit(self, course_name, unit_number):
        self.driver.get('%s/%s/unit?unit=%s' % (
            self.INTEGRATION_SERVER_BASE_URL, course_name, unit_number))

    def load_lesson(self, course_name, unit_number, lesson_number):
        self.driver.get('%s/%s/unit?unit=%s&lesson=%s' % (
            self.INTEGRATION_SERVER_BASE_URL,
            course_name, unit_number, lesson_number))

    def get_sequence_block(self):
        return Sequence(self.driver.find_element_by_css_selector(
            'div.gcb-lesson-content > div > div > div.xblock'))

    def click_cb_prev(self):
        self.driver.find_element_by_css_selector(
            'div.gcb-prev-button > a').click()

    def click_cb_next(self):
        self.driver.find_element_by_css_selector(
            'div.gcb-next-button > a').click()

    def assert_lesson_title(self, title):
        assert self.driver.find_element_by_css_selector(
            '.gcb-lesson-title').text.startswith(title)

    def assert_prev_button_visible(self, is_visible=True):
        display = self.driver.find_element_by_css_selector(
            'div.gcb-prev-button > a').value_of_css_property('display')
        if is_visible:
            assert display == 'block'
        else:
            assert display == 'none'

    def assert_next_button_label(self, label):
        self.assertEqual(label, self.driver.find_element_by_css_selector(
            'div.gcb-next-button > a').text)

    def test_sequence_block(self):
        course_name, unused_title = self.create_new_course()
        self.upload_archive(course_name, 'functional_tests.tar.gz')

        self.load_unit(course_name, 1)

        sequence = self.get_sequence_block()
        sequence.assert_selected(0)
        sequence.click_item(1)
        sequence.assert_selected(1)

        # Same tab is selected when page is reloaded
        self.load_unit(course_name, 1)
        sequence = self.get_sequence_block()
        sequence.assert_selected(1)

        # Test back arrow
        sequence.click_prev()
        sequence.assert_selected(0)

        # Test forward arrow
        sequence.click_next()
        sequence.assert_selected(1)

        # Test multi-page nav with CB arrow buttons. Confirm that can move
        # between the tabs of a sequence and also between pages using the page
        # nav buttons.

        # Start on the first tab of the unit
        sequence.click_item(0)

        sequence.assert_selected(0)
        self.assert_prev_button_visible(is_visible=False)
        self.assert_next_button_label('Next Page')
        self.click_cb_next()

        sequence.assert_selected(1)
        self.assert_prev_button_visible()
        self.assert_next_button_label('Next Page')
        self.click_cb_next()

        sequence = self.get_sequence_block()
        sequence.assert_selected(0)
        self.assert_lesson_title('Subsection 1.2')
        self.assert_prev_button_visible()
        self.assert_next_button_label('End')
        self.click_cb_prev()

        sequence = self.get_sequence_block()
        sequence.assert_selected(1)
        self.assert_lesson_title('Subsection 1.1')
        self.assert_next_button_label('Next Page')
        self.assert_prev_button_visible()
        self.click_cb_prev()

        sequence.assert_selected(0)
        self.assert_prev_button_visible(is_visible=False)

        # Test that navigation with the CB arrow buttons correctly pages back
        # to the last tab of the previous page - even if the state of that
        # sequence has been set to some other value

        # Select the first tab of Subsection 1.1
        self.load_unit(course_name, 1)
        sequence = self.get_sequence_block()
        sequence.click_item(0)
        sequence.assert_selected(0)
        # Jump to Subsection 1.2
        self.load_lesson(course_name, 1, 3)
        # Page back and confirm that the second item of Subsection 1.1 selected
        self.click_cb_prev()
        sequence = self.get_sequence_block()
        sequence.assert_selected(1)

    def test_capa_problem_block(self):
        course_name, unused_title = self.create_new_course()
        self.upload_archive(course_name, 'sample_problems.tar.gz')

        self.load_unit(course_name, 1)

        sequence = self.get_sequence_block()
        sequence.assert_selected(0)
        vertical = Vertical(sequence.get_child(0))
        problem = MultipleChoiceProblem(vertical.get_child(0))

        problem.assert_choice_text(['Green', 'Blue', 'Red', 'Yellow'])

        problem.click_choice(0)
        problem.click_check()
        problem = MultipleChoiceProblem(vertical.get_child(0))
        problem.assert_graded_incorrect(0)
        problem.assert_show_answers_hidden()

        problem.click_choice(1)
        problem.click_check()
        problem = MultipleChoiceProblem(vertical.get_child(0))
        problem.assert_graded_incorrect(1)
        problem.assert_show_answers_hidden()

        problem.click_choice(2)
        problem.click_check()
        problem = MultipleChoiceProblem(vertical.get_child(0))
        problem.assert_graded_correct(2)
        problem.assert_show_answers_visible()

        problem.click_choice(3)
        problem.click_check()
        problem = MultipleChoiceProblem(vertical.get_child(0))
        problem.assert_graded_incorrect(3)
        problem.assert_show_answers_hidden()

        # Reload page and expect choice 3 still selected
        self.load_unit(course_name, 1)
        sequence = self.get_sequence_block()
        sequence.assert_selected(0)
        vertical = Vertical(sequence.get_child(0))
        problem = MultipleChoiceProblem(vertical.get_child(0))
        problem.assert_graded_incorrect(3)

        # Select second tab in sequence
        sequence.click_item(1)
        vertical = Vertical(sequence.get_child(1))
        problem = MultipleSelectionProblem(vertical.get_child(0))
        self.assertEqual('Pick the even numbers:', problem.get_question_text())
        problem.select([0, 2])
        problem.click_check()
        problem.assert_graded_correct()

        problem = MultipleSelectionProblem(vertical.get_child(0))
        problem.select([1, 2])
        problem.click_check()
        problem.assert_graded_incorrect()

        # Reload page and this tab and items 2 and 3 still selected
        self.load_unit(course_name, 1)
        sequence = self.get_sequence_block()
        sequence.assert_selected(1)
        vertical = Vertical(sequence.get_child(0))
        problem = MultipleSelectionProblem(vertical.get_child(0))
        problem.assert_selected([1, 2])
