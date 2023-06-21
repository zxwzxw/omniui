## Copyright (c) 2018-2020, NVIDIA CORPORATION.  All rights reserved.
##
## NVIDIA CORPORATION and its licensors retain all intellectual property
## and proprietary rights in and to this software, related documentation
## and any modifications thereto.  Any use, reproduction, disclosure or
## distribution of this software and related documentation without an express
## license agreement from NVIDIA CORPORATION is strictly prohibited.
##
from .test_base import OmniUiTest
from carb.input import MouseEventType
import omni.kit.app
import omni.ui as ui


STYLE = {
    "TreeView:selected": {"background_color": 0x66FFFFFF},
    "TreeView.Item": {"color": 0xFFCCCCCC},
    "TreeView.Item:selected": {"color": 0xFFCCCCCC},
    "TreeView.Header": {"background_color": 0xFF000000},
}


class ListItem(ui.AbstractItem):
    """Single item of the model"""

    def __init__(self, text):
        super().__init__()
        self.name_model = ui.SimpleStringModel(text)


class ListModel(ui.AbstractItemModel):
    """
    Represents the model for lists. It's very easy to initialize it
    with any string list:
        string_list = ["Hello", "World"]
        model = ListModel(*string_list)
        ui.TreeView(model)
    """

    def __init__(self, *args):
        super().__init__()
        self._children = [ListItem(t) for t in args]

    def get_item_children(self, item):
        """Returns all the children when the widget asks it."""
        if item is not None:
            # Since we are doing a flat list, we return the children of root only.
            # If it's not root we return.
            return []

        return self._children

    def get_item_value_model_count(self, item):
        """The number of columns"""
        return 1

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        return item.name_model


class ListModelDND(ListModel):
    def __init__(self, *args):
        super().__init__(*args)
        self.dropped = []

    def get_drag_mime_data(self, item):
        """Returns Multipurpose Internet Mail Extensions (MIME) data for be able to drop this item somewhere"""
        # As we don't do Drag and Drop to the operating system, we return the string.
        return item.name_model.as_string

    def drop_accepted(self, target_item, source, drop_location=-1):
        return True

    def drop(self, target_item, source, drop_location=-1):
        self.dropped.append(source.name_model.as_string)


class TreeItem(ListItem):
    """Single item of the model"""

    def __init__(self, text):
        super().__init__(text)
        self.children = None

    def get_children(self):
        if self.children is None:
            self.children = [TreeItem(f"{i}") for i in range(3)]
        return self.children


class InfinityModel(ui.AbstractItemModel):
    def __init__(self, crash_test=False):
        super().__init__()
        self._children = [TreeItem("Root")]
        self._crash_test = crash_test
        self._dummy_model = ui.SimpleStringModel("NONE")

    def get_item_children(self, item):
        if item is None:
            return self._children

        if not hasattr(item, "get_children"):
            return []

        children = item.get_children()

        if self._crash_test:
            # Destroy children to see if treeview will crash
            item.children = []

        return children

    def get_item_value_model_count(self, item):
        return 1

    def get_item_value_model(self, item, column_id):
        if hasattr(item, "name_model"):
            return item.name_model
        return self._dummy_model


class InfinityModelTwoColumns(InfinityModel):
    def get_item_value_model_count(self, item):
        return 2


class ListDelegate(ui.AbstractItemDelegate):
    """A very simple delegate"""

    def __init__(self):
        super().__init__()

    def build_branch(self, model, item, column_id, level, expanded):
        """Create a branch widget that opens or closes subtree"""
        pass

    def build_widget(self, model, item, column_id, level, expanded):
        """Create a widget per column per item"""
        value_model = model.get_item_value_model(item, column_id)
        label = value_model.as_string
        ui.Label(label, name=label)

    def build_header(self, column_id):
        """Create a widget for the header"""
        label = f"Header {column_id}"
        ui.Label(label, alignment=ui.Alignment.CENTER, name=label)


class TreeDelegate(ListDelegate):
    def build_branch(self, model, item, column_id, level, expanded):
        label = f"{'- ' if expanded else '+ '}"
        ui.Label(label, width=(level + 1) * 10, alignment=ui.Alignment.RIGHT_CENTER, name=label)


class TestTreeView(OmniUiTest):
    """Testing ui.TreeView"""

    async def test_general(self):
        """Testing default view of ui.TreeView"""
        window = await self.create_test_window()

        self._list_model = ListModel("Simplest", "List", "Of", "Strings")

        with window.frame:
            tree_view = ui.TreeView(self._list_model, root_visible=False, header_visible=False, style=STYLE)

        # Wait one frame to let TreeView initialize the cache.
        await omni.kit.app.get_app().next_update_async()

        # Simulate Shift+Click on the second item when the selection is empty.
        tree_view.extend_selection(self._list_model.get_item_children(None)[1])

        await self.finalize_test()

    async def test_scrolling_header(self):
        """Testing how the ui.TreeView behaves when scrolling"""
        window = await self.create_test_window()

        self._list_model = ListModel(*[f"Item {i}" for i in range(500)])
        self._list_delegate = ListDelegate()

        with window.frame:
            scrolling = ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
            )
            with scrolling:
                tree_view = ui.TreeView(
                    self._list_model, delegate=self._list_delegate, root_visible=False, header_visible=True, style=STYLE
                )

        # Wait one frame to let TreeView initialize the cache.
        await omni.kit.app.get_app().next_update_async()

        scrolling.scroll_y = 1024

        # Wait one frame for ScrollingFrame
        await omni.kit.app.get_app().next_update_async()

        await self.finalize_test()

    async def test_tree(self):
        """Testing how the ui.TreeView show trees"""
        window = await self.create_test_window()

        self._tree_model = InfinityModel(crash_test=False)
        self._tree_delegate = TreeDelegate()

        with window.frame:
            tree_view = ui.TreeView(
                self._tree_model, delegate=self._tree_delegate, root_visible=False, header_visible=False, style=STYLE
            )

        # Wait one frame to let TreeView initialize the cache.
        await omni.kit.app.get_app().next_update_async()

        # Expand
        root = self._tree_model.get_item_children(None)[0]
        first_level = self._tree_model.get_item_children(root)[0]
        tree_view.set_expanded(root, True, False)

        await omni.kit.app.get_app().next_update_async()
        tree_view.set_expanded(first_level, True, False)

        await self.finalize_test()

    async def test_inspector(self):
        """Testing how the ui.TreeView show trees"""
        window = await self.create_test_window()

        self._tree_model = InfinityModelTwoColumns()
        self._tree_delegate = TreeDelegate()

        with window.frame:
            tree_view = ui.TreeView(
                self._tree_model, delegate=self._tree_delegate, root_visible=False, header_visible=True, style=STYLE
            )

        # Wait one frame to let TreeView initialize the cache.
        await omni.kit.app.get_app().next_update_async()

        # Expand
        root = self._tree_model.get_item_children(None)[0]
        first_level = self._tree_model.get_item_children(root)[0]
        tree_view.set_expanded(root, True, False)
        tree_view.set_expanded(first_level, True, False)

        children = ui.Inspector.get_children(tree_view)

        # Check all the children one by one
        self.assertEqual(len(children), 30)
        for child in children:
            self.assertIsInstance(child, ui.Label)
            self.assertEqual(child.name, child.text)

        self.assertEqual(children[0].text, "Header 0")
        self.assertEqual(children[1].text, "Header 1")
        self.assertEqual(children[2].text, "+ ")
        self.assertEqual(children[3].text, "Root")
        self.assertEqual(children[4].text, "+ ")
        self.assertEqual(children[5].text, "Root")
        self.assertEqual(children[6].text, "- ")
        self.assertEqual(children[7].text, "0")
        self.assertEqual(children[8].text, "- ")
        self.assertEqual(children[9].text, "0")
        self.assertEqual(children[10].text, "+ ")
        self.assertEqual(children[11].text, "0")
        self.assertEqual(children[12].text, "+ ")
        self.assertEqual(children[13].text, "0")
        self.assertEqual(children[14].text, "+ ")
        self.assertEqual(children[15].text, "1")
        self.assertEqual(children[16].text, "+ ")
        self.assertEqual(children[17].text, "1")
        self.assertEqual(children[18].text, "+ ")
        self.assertEqual(children[19].text, "2")
        self.assertEqual(children[20].text, "+ ")
        self.assertEqual(children[21].text, "2")
        self.assertEqual(children[22].text, "+ ")
        self.assertEqual(children[23].text, "1")
        self.assertEqual(children[24].text, "+ ")
        self.assertEqual(children[25].text, "1")
        self.assertEqual(children[26].text, "+ ")
        self.assertEqual(children[27].text, "2")
        self.assertEqual(children[28].text, "+ ")
        self.assertEqual(children[29].text, "2")

        await self.finalize_test()

    async def test_query(self):
        """
        Testing if ui.TreeView crashing when querying right after
        initialization.
        """
        window = await self.create_test_window()

        self._tree_model = InfinityModel()
        self._tree_delegate = TreeDelegate()

        with window.frame:
            tree_view = ui.TreeView(
                self._tree_model, delegate=self._tree_delegate, root_visible=False, header_visible=True, style=STYLE
            )

        # Don't wait one frame and don't let TreeView initialize the cache.
        # Trigger dirty
        tree_view.style = {"Label": {"font_size": 14}}
        # Query children and make sure it doesn't crash.
        children = ui.Inspector.get_children(tree_view)

        self.assertEqual(len(children), 3)
        self.assertEqual(children[0].text, "Header 0")
        self.assertEqual(children[1].text, "+ ")
        self.assertEqual(children[2].text, "Root")

        await omni.kit.app.get_app().next_update_async()

        await self.finalize_test()

    async def test_lost_items(self):
        """Testing how the ui.TreeView behaves when the items are destroyed"""
        window = await self.create_test_window()

        self._tree_model = InfinityModel(crash_test=True)
        self._tree_delegate = TreeDelegate()

        with window.frame:
            tree_view = ui.TreeView(
                self._tree_model, delegate=self._tree_delegate, root_visible=False, header_visible=False, style=STYLE
            )

        # Wait one frame to let TreeView initialize the cache.
        await omni.kit.app.get_app().next_update_async()

        # Expand
        tree_view.set_expanded(self._tree_model.get_item_children(None)[0], True, False)

        await omni.kit.app.get_app().next_update_async()

        await self.finalize_test()

    async def test_dnd(self):
        """Testing drag and drop multiple items in ui.TreeView"""
        import omni.kit.ui_test as ui_test

        window = await self.create_test_window(block_devices=False)

        item_names = [f"Item {i}" for i in range(10)]
        _list_model = ListModelDND(*item_names)

        with window.frame:
            tree_view = ui.TreeView(_list_model, root_visible=False, header_visible=False, style=STYLE)

        # Wait one frame to let TreeView initialize the cache.
        await omni.kit.app.get_app().next_update_async()

        item0 = ui_test.find(f"{window.title}//Frame/**/Label[*].text=='Item 0'")
        item1 = ui_test.find(f"{window.title}//Frame/**/Label[*].text=='Item 1'")

        # Select items [1..9]
        tree_view.extend_selection(_list_model.get_item_children(None)[1])
        tree_view.extend_selection(_list_model.get_item_children(None)[len(item_names) - 1])

        await ui_test.emulate_mouse_move(item1.center)
        await ui_test.emulate_mouse_drag_and_drop(item1.center, item0.center)

        await omni.kit.app.get_app().next_update_async()

        await self.finalize_test()

        # Check we received the drop events for all the selection
        for dropped, reference in zip(_list_model.dropped, item_names[1:]):
            self.assertEqual(dropped, reference)

    async def test_dnd_delegate_callbacks(self):
        moved = [0]
        pressed = [0]
        released = [0]

        class TestDelegate(ui.AbstractItemDelegate):
            def build_widget(self, model, item, column_id, level, expanded):
                if item is None:
                    return
                if column_id == 0:
                    with ui.HStack(
                        mouse_pressed_fn=lambda x, y, b, m: self._on_item_mouse_pressed(item),
                        mouse_released_fn=lambda x, y, b, m: self._on_item_mouse_released(item),
                        mouse_moved_fn=lambda x, y, m, t: self._on_item_mouse_moved(x, y),
                    ):
                        ui.Label(item.name_model.as_string)

            def _on_item_mouse_moved(self, x, y):
                moved[0] += 1

            def _on_item_mouse_pressed(self, item):
                pressed[0] += 1

            def _on_item_mouse_released(self, item):
                released[0] += 1

        import omni.kit.ui_test as ui_test

        window = await self.create_test_window(block_devices=False)

        _model = ListModel("Test 1", "Test 2", "Test 3", "Test 4", "Test 5")
        _delegate = TestDelegate()

        with window.frame:
            ui.TreeView(_model, delegate=_delegate, root_visible=False)

        # Wait one frame to let TreeView initialize the cache.
        await omni.kit.app.get_app().next_update_async()

        item1 = ui_test.find(f"{window.title}//Frame/**/Label[*].text=='Test 1'")
        item5 = ui_test.find(f"{window.title}//Frame/**/Label[*].text=='Test 5'")

        await ui_test.emulate_mouse_move(item1.center)

        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
        await ui_test.human_delay(5)

        # Check pressed is called
        self.assertEqual(pressed[0], 1)
        self.assertEqual(moved[0], 0)

        await ui_test.input.emulate_mouse_slow_move(item1.center, item5.center)
        await ui_test.human_delay(5)

        # We have not released the mouse yet
        self.assertEqual(released[0], 0)
        self.assertTrue(moved[0] > 0)

        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP)
        await ui_test.human_delay(5)

        # Checked release is called
        self.assertEqual(released[0], 1)

        await self.finalize_test_no_image()

    async def test_separate_window(self):
        class ListItem(ui.AbstractItem):
            """Single item of the model"""

            def __init__(self, text):
                super().__init__()
                self.name_model = ui.SimpleStringModel(text)

        class ListModel(ui.AbstractItemModel):
            """
            Represents the model for lists. It's very easy to initialize it
            with any string list:
                string_list = ["Hello", "World"]
                model = ListModel(*string_list)
                ui.TreeView(model)
            """

            def __init__(self, items):
                super().__init__()
                self._children = [ListItem(t) for t in items]

            def get_item_children(self, item):
                """Returns all the children when the widget asks it."""
                if item is not None:
                    # Since we are doing a flat list, we return the children of root only.
                    # If it's not root we return.
                    return []

                return self._children

            def get_item_value_model_count(self, item):
                """The number of columns"""
                return 1

            def get_item_value_model(self, item, column_id):
                """
                Return value model.
                It's the object that tracks the specific value.
                In our case we use ui.SimpleStringModel.
                """
                return item.name_model

        class ListDelegate(ui.AbstractItemDelegate):
            """A very simple delegate"""

            def __init__(self):
                super().__init__()

            def build_branch(self, model, item, column_id, level, expanded):
                """Create a branch widget that opens or closes subtree"""
                pass

            def build_widget(self, model, item, column_id, level, expanded):
                """Create a widget per column per item"""
                value_model = model.get_item_value_model(item, column_id)
                label = value_model.as_string
                with ui.Frame(height=0, separate_window=True):
                    ui.Label(label, name=label)

            def build_header(self, column_id):
                """Create a widget for the header"""
                label = f"Header {column_id}"
                ui.Label(label, alignment=ui.Alignment.CENTER, name=label)

        window = await self.create_test_window()

        list_model = ListModel([f"Test {i}" for i in range(500)])
        list_delegate = ListDelegate()
        with window.frame:
            scrolling = ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_ON,
            )
            with scrolling:
                tree_view = ui.TreeView(list_model, delegate=list_delegate, root_visible=False, header_visible=True)

        await omni.kit.app.get_app().next_update_async()
        scrolling.scroll_y = 500
        await omni.kit.app.get_app().next_update_async()

        await self.finalize_test()

    async def test_separate_window_dnd(self):
        class TestItem(ui.AbstractItem):
            def __init__(self, text):
                super().__init__()
                self.text_model = text

            def __repr__(self):
                return self.text_model

        class TestModel(ui.AbstractItemModel):
            def __init__(self, *args):
                super().__init__()
                self._children = [TestItem(i) for i in args]

            def get_item_children(self, item):
                if item is not None:
                    return []
                return self._children

            def get_item_value_model_count(self, item):
                return 1

            def get_drag_mime_data(self, item):
                return item.text_model

        class TestDelegate(ui.AbstractItemDelegate):
            def build_widget(self, model, item, column_id, level, expanded):
                if item is None:
                    return
                if column_id == 0:
                    with ui.Frame(separate_window=True):
                        ui.Label(item.text_model)

        import omni.kit.ui_test as ui_test

        window = await self.create_test_window(block_devices=False)

        model = TestModel(*[f"Test #{i}" for i in range(50)])
        delegate = TestDelegate()

        with window.frame:
            tree_view = ui.TreeView(model, delegate=delegate, root_visible=False)

        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()

        ref = ui_test.WidgetRef(tree_view, "")
        await omni.kit.app.get_app().next_update_async()

        await ui_test.emulate_mouse_move(ref.center)
        await ui_test.emulate_mouse_click()

        await ui_test.input.emulate_mouse_slow_move(ref.center, ui_test.Vec2(ref.center.x * 0.1, ref.center.y * 0.25))

        await ui_test.human_delay(5)
        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
        await ui_test.human_delay(5)

        await ui_test.input.emulate_mouse_slow_move(
            ui_test.Vec2(ref.center.x * 0.1, ref.center.y * 0.25), ui_test.Vec2(ref.center.x * 0.1, ref.center.y * 0.5)
        )
        await ui_test.human_delay(30)

        await self.finalize_test()

        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP)

    async def test_right_click(self):
        from functools import partial

        clicked = [0, 0, 0]

        class TestItem(ui.AbstractItem):
            def __init__(self, text):
                super().__init__()
                self.text_model = text

            def __repr__(self):
                return self.text_model

        class TestModel(ui.AbstractItemModel):
            def __init__(self, *args):
                super().__init__()
                self._children = [TestItem(i) for i in args]

            def get_item_children(self, item):
                if item is not None:
                    return []
                return self._children

            def get_item_value_model_count(self, item):
                return 1

            def get_drag_mime_data(self, item):
                return item.text_model

        class TestDelegate(ui.AbstractItemDelegate):
            def build_widget(self, model, item, column_id, level, expanded):
                if item is None:
                    return
                if column_id == 0:
                    with ui.HStack(mouse_released_fn=partial(self._show_context_menu, item)):
                        ui.Label(item.text_model)

            def _show_context_menu(self, item, x, y, button, *_):
                clicked[button] += 1

        class TestWidget:
            def __init__(self):
                self._model = TestModel(*[f"Test#{i}" for i in range(40)])
                self._delegate = TestDelegate()
                self._bookmark_tree_widget = ui.TreeView(self._model, delegate=self._delegate, root_visible=False)
                
        import omni.kit.ui_test as ui_test
        window = await self.create_test_window(block_devices=False)
        with window.frame:
            widget = TestWidget()

        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()

        ref = ui_test.WidgetRef(widget._bookmark_tree_widget, "")

        await omni.kit.app.get_app().next_update_async()

        await ui_test.emulate_mouse_move(ui_test.Vec2(20, 20))
        await ui_test.emulate_mouse_click()

        await omni.kit.app.get_app().next_update_async()

        await ui_test.emulate_mouse_click(right_click=True)

        await omni.kit.app.get_app().next_update_async()

        self.assertEqual(clicked[0], 1)
        self.assertEqual(clicked[1], 1)
        self.assertEqual(clicked[2], 0)

        await self.finalize_test_no_image()
