// Finder Services provider installed per user from the packaged PicView.app.
#import <AppKit/AppKit.h>

@interface PicViewOpenService : NSObject
- (void)openInPicView:(NSPasteboard *)pasteboard
            userData:(NSString *)userData
               error:(NSString **)error;
@end

@implementation PicViewOpenService
- (void)openInPicView:(NSPasteboard *)pasteboard
            userData:(NSString *)userData
               error:(NSString **)error {
    NSArray<NSURL *> *items = [pasteboard readObjectsForClasses:@[[NSURL class]]
        options:@{NSPasteboardURLReadingFileURLsOnlyKey: @YES}];
    NSMutableArray<NSString *> *arguments = [NSMutableArray arrayWithArray:
        @[@"-n", @"-b", @"io.github.codemee.picview", @"--args"]];
    NSSet<NSString *> *extensions = [NSSet setWithArray:
        @[@"jpg", @"jpeg", @"png", @"webp", @"bmp", @"gif", @"tif", @"tiff", @"svg"]];
    for (NSURL *item in items) {
        if (!item.isFileURL) continue;
        NSNumber *directory = nil;
        [item getResourceValue:&directory forKey:NSURLIsDirectoryKey error:nil];
        if (directory.boolValue || [extensions containsObject:item.pathExtension.lowercaseString]) {
            [arguments addObject:item.path];
        }
    }
    if (arguments.count == 4) return;
    NSTask *task = [NSTask new];
    task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/open"];
    task.arguments = arguments;
    NSError *launchError = nil;
    if (![task launchAndReturnError:&launchError] && error) {
        *error = launchError.localizedDescription;
    }
}
@end

int main(void) {
    @autoreleasepool {
        PicViewOpenService *provider = [PicViewOpenService new];
        NSRegisterServicesProvider(provider, @"PicViewOpenService");
        [[NSRunLoop currentRunLoop] run];
    }
    return 0;
}
