from abc import abstractmethod
from enum import Enum
import obspython as obs


# GLOBAL VARIABLES
playlist = None
playout_scene = None
playout_scene_name = None
selected_item_index = None
current_media_path = None
current_cg_scene_name = None
cg_event_type = None


# helper functions
def play_next(cd):
    playlist.playNext()

def playlist_play(props, p):
    playlist.playlistPlay()

def playlist_stop(props, p):
    playlist.playlistStop()

def add_video(props, p):
    playlist.itemInsert(selected_item_index, ItemVideo(playlist.getNextId(), current_media_path))

def clear_playlist(props, p):
    playlist.itemClear()

def add_cg(props, p):
    playlist.itemInsert(selected_item_index, ItemEvent(playlist.getNextId(), playlist, cg_event_type, current_cg_scene_name))

def remove_item(props, p):
    playlist.itemRemoveAtIndex(selected_item_index)

def print_items(props, p):
    s = '======= START PLAYLIST ITEMS PRINT =======\n'
    for idx, x in enumerate(playlist.items):
        s += f'{idx} - '
        if type(x) == ItemVideo:
            s += x.mediaAbsolutePath + '\n'
        elif type(x) == ItemEvent:
            scene_name = '' if x.sceneName is None else x.sceneName
            s += f'{x.eventType.name}: {scene_name}\n'
    s += '======= END PLAYLIST ITEMS PRINT   ======='
    print(s)
    return False


# Playlist Class
class Playlist:
    
    def __init__(self, refScene, baseSize: tuple) -> None:
        self.refScene = refScene
        self.itemId = 0

        # lists
        self.items = []
        self.cgItems = []  # a list is used so that we can layer Scenes

        self.playing = False
        self.itemIndexPrev = None
        self.itemIndexCurrent = None

        self.itemTransformInfo = None
        self._createTransformInfo(baseSize)

    def getNextId(self) -> str:
        self.itemId += 1
        return str(self.itemId)

    # playlist controls
    def playlistPlay(self, idx=0) -> None:
        if self.playing:
            self.destroyUntilMedia()
        if idx < 0:
            idx = 0
        if idx >= len(self.items):
            return
        
        self.itemIndexCurrent = idx
        self.itemIndexPrev = None
        self.playing = True
        self.playNext()

    def playlistStop(self) -> None:
        self.destroyUntilMedia()
        self.cgClear()
        self.playing = False
        self.itemIndexPrev = None
        self.itemIndexCurrent = None
    
    def destroyPrev(self) -> None:
        if self.itemIndexPrev is not None:
            self.items[self.itemIndexPrev].destroy()

    def destroyUntilMedia(self) -> None:
        if len(self.items) == 0:
            return
        idx = self.itemIndexPrev
        item = self.items[idx]
        while idx >= 0 and type(item) != ItemEvent:
            item.destroy()
            idx -= 1
            item = self.items[idx]

    def playNext(self) -> None:

        # clean up previous item
        self.destroyPrev()

        # check if last item was last
        if self.itemIndexCurrent >= len(self.items):
            self.playing = False
            self.itemIndexPrev = None
            self.itemIndexCurrent = None
            return

        # set previous item to current
        self.itemIndexPrev = self.itemIndexCurrent
        self.itemIndexCurrent += 1

        # setup current item and create
        currentItem = self.items[self.itemIndexPrev]
        currentItem.setRefScene(self.refScene)
        currentItem.create(self.itemTransformInfo)

        # making sure cg items are at the top of the order
        for idx, x in enumerate(self.cgItems):
            obs.obs_sceneitem_set_order_position(x.refSceneItem, idx+1)
        if type(currentItem) != ItemEvent:
            obs.obs_sceneitem_set_order_position(currentItem.refSceneItem, 0)

    def itemInsert(self, idx: int, item):
        if idx >= len(self.items) or idx < 0:
            self.items.append(item)
        else:
            self.items.insert(idx, item)

    def itemRemoveAtIndex(self, idx):
        if idx >= len(self.items) or idx < 0 or (self.playing and idx == self.itemIndexPrev):
            return
        self.items.pop(idx)
    
    def itemClear(self):
        if not self.playing:
            self.items.clear()

    def cgClear(self):

        # get the sceneitem ref from playlist cgItems
        for x in self.cgItems:
            obs.obs_sceneitem_remove(x.refSceneItem)
        
        # clear list
        self.cgItems.clear()

    # stretch functions
    def _createTransformInfo(self, baseSize: tuple):
        self.itemTransformInfo = obs.obs_transform_info()
        self.itemTransformInfo.alignment = 5
        self.itemTransformInfo.bounds_type = obs.OBS_BOUNDS_STRETCH
        self.itemTransformInfo.bounds_alignment = 1
        bounds = obs.vec2()
        bounds.x, bounds.y = baseSize
        self.itemTransformInfo.bounds = bounds


# Playlist item
class Item:
    def __init__(self, itemId: str) -> None:
        self.itemId = itemId
        self.refScene = None
    def setRefScene(self, refScene):
        self.refScene = refScene
    # create and and execute item
    @abstractmethod
    def create(self, transformInfo) -> None:
        pass
    # in quotes 'destructor', release any references from obs and/or cleans up internally
    @abstractmethod
    def destroy(self) -> None:
        pass


# Local & External Video
class ItemVideo(Item):
    def __init__(self, itemId: str, mediaAbsolutePath: str) -> None:
        super().__init__(itemId)

        self.mediaAbsolutePath = mediaAbsolutePath

        self.refSource = None
        self.refSceneItem = None
        self.signalHandler = None

    def create(self, transformInfo) -> None:

        # settings
        settings = obs.obs_data_create()
        obs.obs_data_set_string(settings, 'local_file', self.mediaAbsolutePath)
        obs.obs_data_set_bool(settings, 'restart_on_activate', False)
        obs.obs_data_set_bool(settings, 'clear_on_media_end', False)

        # create the source
        self.refSource = obs.obs_source_create('ffmpeg_source', self.itemId, settings, None)

        # release settings
        obs.obs_data_release(settings)

        # add it to a scene
        self.refSceneItem = obs.obs_scene_add(self.refScene, self.refSource)

        # transforms
        obs.obs_sceneitem_set_info(self.refSceneItem, transformInfo)

        # signal handler
        self.signalHandler = obs.obs_source_get_signal_handler(self.refSource)
        obs.signal_handler_connect(self.signalHandler, 'media_ended', play_next)
    
    def destroy(self) -> None:
        obs.signal_handler_disconnect(self.signalHandler, 'media_ended', play_next)
        obs.obs_sceneitem_remove(self.refSceneItem)
        obs.obs_source_release(self.refSource)

# Events
class EventType(Enum):
    CG_ON = 0
    CG_OFF = 1
    CG_CLEAR = 2

class ItemEvent(Item):
    def __init__(self, itemId: str, playlist: Playlist, eventType: EventType, sceneName: str = None) -> None:
        super().__init__(itemId)
        
        self.playlist = playlist
        self.eventType = eventType
        self.sceneName = sceneName

        self.refSceneItem = None
        
    def create(self, transformInfo) -> None:
        if self.eventType == EventType.CG_ON and self.sceneName is not None:
            self.createOnEvent()
        elif self.eventType == EventType.CG_OFF and self.sceneName is not None:
            self.createOffEvent()
        elif self.eventType == EventType.CG_CLEAR:
            self.createClearEvent()
        else:
            self.playlist.playNext()

    def createOnEvent(self) -> None:
        
        # check if scene already added to cg items
        for x in playlist.cgItems:
            if x.sceneName == self.sceneName:
                self.playlist.playNext()
                return

        # get the cg scene reference
        refCGScene = obs.obs_get_scene_by_name(self.sceneName)

        # get it's source reference
        refSource = obs.obs_scene_get_source(refCGScene)
        
        # add it to playlist scene
        self.refSceneItem = obs.obs_scene_add(self.refScene, refSource)

        # add sceneitem ref to playlist cgItems
        self.playlist.cgItems.append(self)

        # release scene reference
        obs.obs_scene_release(refCGScene)

        # playnext
        self.playlist.playNext()

    def createOffEvent(self) -> None:
        
        cgOnObj = None

        # get the sceneitem ref from playlist cgItems
        for x in playlist.cgItems:
            if x.sceneName == self.sceneName:
                cgOnObj = x
        
        if cgOnObj is None:
            self.playlist.playNext()

        # remove the item from scene
        obs.obs_sceneitem_remove(cgOnObj.refSceneItem)

        # remove sceneitem from playlist cgItems
        self.playlist.cgItems.remove(cgOnObj)

        # play next
        self.playlist.playNext()

    def createClearEvent(self) -> None:

        self.playlist.cgClear()

        # play next
        self.playlist.playNext()


def script_load(settings) -> None:
    global video_info
    global playlist
    video_info = obs.obs_video_info()
    obs.obs_get_video_info(video_info)
    playlist = Playlist(playout_scene, (video_info.base_width, video_info.base_height))

def script_unload() -> None:
    obs.obs_scene_release(playout_scene)

def script_description() -> str:
    return 'A simple "Playout" System for OBS.\nNote: Doesn\'t work very smoothly and generally unstable, hence it will be rewritten. Please see "github.com/safatdev" for an updated version.\n'

def script_properties():
    props = obs.obs_properties_create()
    
    # Playout Scene Selector
    obs.obs_properties_add_text(props, 'playout_scene_name', 'Playout Scene Name', obs.OBS_TEXT_DEFAULT)

    # Item Index
    obs.obs_properties_add_int(props, 'item_index', 'Selection Index', -1, 99999, 1)
    
    # Playlist Controls
    obs.obs_properties_add_button(props, 'print_items', 'Print Playlist Items [Log]', print_items)
    obs.obs_properties_add_button(props, 'play_button', 'Playlist Play [idx]', playlist_play)
    obs.obs_properties_add_button(props, 'stop_button', 'Playlist Stop', playlist_stop)
    obs.obs_properties_add_button(props, 'clear_button', 'Playlist Clear', clear_playlist)

    obs.obs_properties_add_text(props, 'play_explainer', 'Use Index -1 to append Items at the End', obs.OBS_TEXT_INFO)

    # Add Video
    obs.obs_properties_add_path(props, 'media_path', 'Video Path', obs.OBS_PATH_FILE, 'Video Files (*mp4 *ts *mov *flv *mkv *avi *gif *webm)', None)
    obs.obs_properties_add_button(props, 'add_video_button', 'Add Video [idx]', add_video)

    # Add Events
    obs.obs_properties_add_text(props, 'cg_explainer', 'Make sure name is not the same as Playout Scene.', obs.OBS_TEXT_INFO)
    obs.obs_properties_add_text(props, 'cg_scene_name', 'CG Scene Name', obs.OBS_TEXT_DEFAULT)

    # Type of CG
    event_type_list = obs.obs_properties_add_list(props, 'cg_event_type', 'Event Type', obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_INT)
    obs.obs_property_list_add_int(event_type_list, 'CG ON', 0)
    obs.obs_property_list_add_int(event_type_list, 'CG OFF', 1)
    obs.obs_property_list_add_int(event_type_list, 'CG CLEAR', 2)

    obs.obs_properties_add_button(props, 'add_cg_button', 'Add CG Event [idx]', add_cg)

    # Remove Item
    obs.obs_properties_add_button(props, 'remove_item_button', 'Remove Item [idx]', remove_item)

    return props

def script_defaults(settings):
    obs.obs_data_set_string(settings, 'playout_scene_name', 'Playout')
    obs.obs_data_set_int(settings, 'item_index', -1)

def script_update(settings) -> None:
    
    global selected_item_index
    global current_media_path

    global playout_scene
    global playout_scene_name
    global current_cg_scene_name
    global cg_event_type

    updated_playout_scene_name = obs.obs_data_get_string(settings, 'playout_scene_name')
    selected_item_index = obs.obs_data_get_int(settings, 'item_index')
    current_media_path = obs.obs_data_get_string(settings, 'media_path')
    current_cg_scene_name = obs.obs_data_get_string(settings, 'cg_scene_name')
    cg_event_type = EventType(obs.obs_data_get_int(settings, 'cg_event_type'))

    # playout scene name changed
    if updated_playout_scene_name != playout_scene_name:
        playout_scene_name = updated_playout_scene_name
        if playout_scene is not None:
            obs.obs_scene_release(playout_scene)
        playout_scene = obs.obs_get_scene_by_name(playout_scene_name)
        playlist.refScene = playout_scene